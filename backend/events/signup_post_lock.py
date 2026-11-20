"""Per-event pending flag, dirty time and edit lock for the Discord signup post.

Shared by the web process (which marks a post edit pending) and the Celery
worker (which takes the lock around an edit). Every Redis failure fails open:
the caller proceeds as if the flag was set or the lock was taken.
"""

import secrets
import time

import redis
from django.conf import settings

from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from config.signup_post import SignupPostConfig
from telemetry.logging import get_logger

log = get_logger(__name__)

FAIL_OPEN = "fail-open"
# Compare-and-delete in one round trip, so an expired lock retaken by another
# run is never deleted by the previous holder.
_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)
_TAGS = ["events", "signup"]
DIRTY_TTL_SECONDS = 3600


def _config() -> SignupPostConfig:
    return settings.SIGNUP_POST


def pending_key(event_id: int) -> str:
    return namespaced_key(f"events:signup_post:pending:{event_id}")


def lock_key(event_id: int) -> str:
    return namespaced_key(f"events:signup_post:lock:{event_id}")


def dirty_key(event_id: int) -> str:
    return namespaced_key(f"events:signup_post:dirty:{event_id}")


def now_ms() -> int:
    return int(time.time() * 1000)


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


def mark_dirty(event_id: int, since_ms: int | None = None) -> None:
    """Record when the oldest change the post does not show yet was made.

    A restored ``since_ms`` overwrites a newer time, so the oldest one is kept.
    """
    if _config().disabled:
        return
    try:
        get_redis_client().set(
            dirty_key(event_id),
            str(now_ms() if since_ms is None else since_ms),
            nx=since_ms is None,
            ex=DIRTY_TTL_SECONDS,
        )
    except redis.RedisError as exc:
        _unavailable(event_id, "mark_dirty", "dispatch", exc)


def clear_pending(event_id: int) -> int | None:
    """Clear the pending flag and return the dirty time it covered, in ms."""
    if _config().disabled:
        return None
    try:
        pipe = get_redis_client().pipeline()
        pipe.delete(pending_key(event_id))
        pipe.getdel(dirty_key(event_id))
        _, since = pipe.execute()
    except redis.RedisError as exc:
        _unavailable(event_id, "clear_pending", "dispatch", exc)
        return None
    return int(since) if since else None


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
    try:
        release = get_redis_client().register_script(_RELEASE_LUA)
        release(keys=[lock_key(event_id)], args=[token])
    except redis.RedisError as exc:
        _unavailable(event_id, "release_lock", "celery", exc)
