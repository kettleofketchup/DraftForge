"""Which orgs get Discord name syncs, plus the per-guild sync lock and enqueue."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app.tasks.discord_name_sync import sync_org_discord_names
from org.models import Organization
from telemetry.logging import get_logger

log = get_logger(__name__)

ACTIVE_LOOKBACK: timedelta = timedelta(days=3)
ACTIVE_LOOKAHEAD: timedelta = timedelta(days=7)
GUILD_SYNC_LOCK_TTL_S: int = 600

_BROKER_TIMEOUT_S = 0.5


def _guild_lock_key(guild_id: str) -> str:
    return f"discord_name_sync_guild_{guild_id}"


def active_org_ids(org_ids: Iterable[int], *, now: datetime | None = None) -> set[int]:
    """Orgs with a tournament in progress, or a tournament or event in the window."""
    ids = set(org_ids)
    if not ids:
        return set()
    now = now or timezone.now()
    start, end = now - ACTIVE_LOOKBACK, now + ACTIVE_LOOKAHEAD
    tournaments = Q(leagues__tournaments__state="in_progress") | Q(
        leagues__tournaments__date_played__range=(start, end)
    )
    events = Q(events__scheduled_at__range=(start, end))
    return set(
        Organization.objects.nocache()
        .filter(pk__in=ids)
        .filter(tournaments | events)
        .values_list("pk", flat=True)
        .distinct()
    )


def guild_sync_lock(guild_id: str) -> bool:
    return bool(cache.add(_guild_lock_key(guild_id), 1, GUILD_SYNC_LOCK_TTL_S))


def release_guild_sync_lock(guild_id: str) -> None:
    cache.delete(_guild_lock_key(guild_id))


def _publish_org_name_sync(org_id: int) -> None:
    try:
        celery_app = sync_org_discord_names.app
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
