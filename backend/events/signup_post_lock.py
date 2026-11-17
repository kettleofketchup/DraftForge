"""Per-event pending flag and edit lock for the Discord signup post.

Shared by the web process (which marks a post edit pending) and the Celery
worker (which takes the lock around an edit). Every Redis failure fails open:
the caller proceeds as if the flag was set or the lock was taken.
"""

import secrets

import redis
from django.conf import settings

from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from config.signup_post import SignupPostConfig
from telemetry.logging import get_logger

log = get_logger(__name__)

FAIL_OPEN = "fail-open"
_TAGS = ["events", "signup"]


def _config() -> SignupPostConfig:
    return settings.SIGNUP_POST


def pending_key(event_id: int) -> str:
    return namespaced_key(f"events:signup_post:pending:{event_id}")


def lock_key(event_id: int) -> str:
    return namespaced_key(f"events:signup_post:lock:{event_id}")


def _unavailable(event_id: int, op: str, subsystem: str, exc: redis.RedisError) -> None:
    log.warning(
        "signup_post_lock_unavailable",
        system="discord",
        subsystem=subsystem,
        tags=_TAGS,
        tags_csv=",".join(_TAGS),
        event_id=event_id,
        op=op,
        error=str(exc),
    )


def mark_pending(event_id: int) -> bool:
    """Set the pending flag; True when this call set it (or the lock is off)."""
    config = _config()
    if config.disabled:
        return True
    try:
        return bool(
            get_redis_client().set(
                pending_key(event_id), "1", nx=True, ex=config.pending_ttl_seconds
            )
        )
    except redis.RedisError as exc:
        _unavailable(event_id, "mark_pending", "dispatch", exc)
        return True


def clear_pending(event_id: int) -> None:
    if _config().disabled:
        return
    try:
        get_redis_client().delete(pending_key(event_id))
    except redis.RedisError as exc:
        _unavailable(event_id, "clear_pending", "dispatch", exc)


def acquire_lock(event_id: int) -> str | None:
    """Return a release token, ``FAIL_OPEN`` when unlocked, or None when held."""
    config = _config()
    if config.disabled:
        return FAIL_OPEN
    token = secrets.token_hex(16)
    try:
        taken = get_redis_client().set(
            lock_key(event_id), token, nx=True, ex=config.lock_seconds
        )
    except redis.RedisError as exc:
        _unavailable(event_id, "acquire_lock", "celery", exc)
        return FAIL_OPEN
    return token if taken else None


def release_lock(event_id: int, token: str) -> None:
    """Delete the lock only while it still holds ``token``."""
    if token == FAIL_OPEN or _config().disabled:
        return
    key = lock_key(event_id)
    try:
        client = get_redis_client()
        if client.get(key) == token:
            client.delete(key)
    except redis.RedisError as exc:
        _unavailable(event_id, "release_lock", "celery", exc)
