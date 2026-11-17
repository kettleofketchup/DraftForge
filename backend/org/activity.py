"""Per-org activity tracking in the Django cache, gating Discord name syncs."""

import time
from collections.abc import Iterable

from cacheops.conf import settings as cacheops_settings
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from rest_framework.request import Request

from app.auth import InternalServiceAuth, InternalServiceUser
from app.models import Organization
from app.tasks.discord_name_sync import sync_org_discord_names
from config.celery import app as celery_app
from telemetry.logging import get_logger

log = get_logger(__name__)

ORG_ACTIVITY_TTL_S: int = 3 * 24 * 3600
ORG_SYNC_DEBOUNCE_S: int = 300
GUILD_SYNC_LOCK_TTL_S: int = 600

_DUMMY_CACHE_BACKEND = "django.core.cache.backends.dummy.DummyCache"
_BROKER_TIMEOUT_S = 0.5


def _activity_key(org_id: int) -> str:
    return f"org_activity_{org_id}"


def _guild_lock_key(guild_id: str) -> str:
    return f"discord_name_sync_guild_{guild_id}"


def activity_tracking_enabled() -> bool:
    if settings.CACHES.get("default", {}).get("BACKEND") == _DUMMY_CACHE_BACKEND:
        return False
    return bool(cacheops_settings.CACHEOPS_ENABLED)


def _is_real_user(request: Request) -> bool:
    if isinstance(
        getattr(request, "successful_authenticator", None), InternalServiceAuth
    ):
        return False
    user = getattr(request, "user", None)
    if isinstance(user, InternalServiceUser):
        return False
    return bool(getattr(user, "is_authenticated", False))


def _org_guild_id(org_id: int) -> str | None:
    guild_id = (
        Organization.objects.filter(pk=org_id)
        .values_list("discord_server_id", flat=True)
        .first()
    )
    return guild_id or None


def touch_org_activity(
    request: Request, org_id: int | None, *, guild_id: str | None = None
) -> None:
    if org_id is None or not activity_tracking_enabled():
        return
    try:
        if not _is_real_user(request):
            return
        key = _activity_key(org_id)
        if not cache.add(key, time.time(), ORG_ACTIVITY_TTL_S):
            cache.touch(key, ORG_ACTIVITY_TTL_S)
            return
        guild = guild_id if guild_id is not None else _org_guild_id(org_id)
        if not guild:
            return
        if not cache.add(f"discord_name_sync_pending_{guild}", 1, ORG_SYNC_DEBOUNCE_S):
            return
        enqueue_org_name_sync(org_id)
    except Exception:
        log.warning(
            "org_activity_touch_failed",
            system="org",
            subsystem="activity",
            org_id=org_id,
            exc_info=True,
        )


def active_org_ids(org_ids: Iterable[int]) -> set[int]:
    keys = {_activity_key(org_id): org_id for org_id in org_ids}
    if not keys:
        return set()
    found = cache.get_many(list(keys))
    return {keys[key] for key in found}


def guild_sync_lock(guild_id: str) -> bool:
    return bool(cache.add(_guild_lock_key(guild_id), 1, GUILD_SYNC_LOCK_TTL_S))


def release_guild_sync_lock(guild_id: str) -> None:
    cache.delete(_guild_lock_key(guild_id))


def _publish_org_name_sync(org_id: int) -> None:
    try:
        transport = dict(celery_app.conf.broker_transport_options or {})
        transport.update(
            socket_connect_timeout=_BROKER_TIMEOUT_S, socket_timeout=_BROKER_TIMEOUT_S
        )
        with celery_app.connection_for_write(
            connect_timeout=_BROKER_TIMEOUT_S, transport_options=transport
        ) as conn:
            sync_org_discord_names.apply_async(
                args=[org_id], retry=False, connection=conn
            )
    except Exception:
        log.warning(
            "name_sync_enqueue_failed",
            system="org",
            subsystem="activity",
            org_id=org_id,
            exc_info=True,
        )
        return
    log.info("name_sync_enqueued", system="org", subsystem="activity", org_id=org_id)


def enqueue_org_name_sync(org_id: int) -> None:
    transaction.on_commit(lambda: _publish_org_name_sync(org_id))
