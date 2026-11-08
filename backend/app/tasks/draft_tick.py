"""Shared draft tick runner, parameterised by a Redis key/span prefix.

herodraft_tick.py binds this module to "herodraft". Drivers supply the
draft-specific steps via TickDriver.

Diagnostic events when ticks misbehave:
  tick_step_slow      - any sub-step >300ms
  tick_loop_stalled   - gap between consecutive ticks >1.5s (event-loop blocked)
  tick_slow           - whole iteration >1.5s
"""

import threading
from typing import NamedTuple, Protocol, runtime_checkable

import redis
from django.conf import settings

from telemetry.logging import get_logger

log = get_logger(__name__)

TICK_STEP_SLOW_THRESHOLD_S: float = 0.3
TICK_GAP_STALL_THRESHOLD_S: float = 1.5
TICK_ITERATION_SLOW_THRESHOLD_S: float = 1.5

LOCK_TIMEOUT: int = 10
CONN_COUNT_TTL_SECONDS: int = 300
HEARTBEAT_INTERVAL_SECONDS: int = 3
HEARTBEAT_STALE_SECONDS: int = 9
HEARTBEAT_TTL: int = 30
CAPTAIN_CHANNEL_TTL: int = 300

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        redis_host = getattr(settings, "REDIS_HOST", "localhost")
        _redis_client = redis.Redis(host=redis_host, port=6379, db=2, decode_responses=True)
    return _redis_client


def heartbeat_key(prefix: str, draft_id: int, user_id: int) -> str:
    return f"{prefix}:{draft_id}:captain:{user_id}:heartbeat"


def captain_channel_key(prefix: str, draft_id: int, user_id: int) -> str:
    return f"{prefix}:{draft_id}:captain:{user_id}:channel"


def conn_count_key(prefix: str, draft_id: int) -> str:
    return f"{prefix}:connections:{draft_id}"


def lock_key(prefix: str, draft_id: int) -> str:
    return f"{prefix}:tick_lock:{draft_id}"


def increment_connection_count(prefix: str, draft_id: int) -> int:
    """Increment WebSocket connection count for a draft. Returns new count."""
    r = get_redis_client()
    key = conn_count_key(prefix, draft_id)
    count: int = r.incr(key)
    r.expire(key, CONN_COUNT_TTL_SECONDS)
    log.debug(
        "connection_count_incremented",
        system="websocket",
        subsystem="timer",
        prefix=prefix,
        draft_id=draft_id,
        count=count,
    )
    return count


def decrement_connection_count(prefix: str, draft_id: int) -> int:
    """Decrement WebSocket connection count for a draft. Returns new count."""
    r = get_redis_client()
    key = conn_count_key(prefix, draft_id)
    count: int = r.decr(key)
    if count <= 0:
        r.delete(key)
        count = 0
    log.debug(
        "connection_count_decremented",
        system="websocket",
        subsystem="timer",
        prefix=prefix,
        draft_id=draft_id,
        count=count,
    )
    return count


def get_connection_count(prefix: str, draft_id: int) -> int:
    """Get current WebSocket connection count for a draft."""
    count = get_redis_client().get(conn_count_key(prefix, draft_id))
    return int(count) if count else 0


class TaskInfo(NamedTuple):
    stop_event: threading.Event
    thread: threading.Thread


@runtime_checkable
class TickDriver(Protocol):
    prefix: str  # Redis key + span prefix; MUST equal the consumer's get_redis_prefix()
    system: str  # structlog system tag for loop logs

    async def check_resume_countdown(self, draft_id: int) -> None: ...

    async def check_captain_heartbeats(self, draft_id: int) -> None: ...

    async def broadcast_tick(self, draft_id: int) -> None: ...

    async def check_timeout(self, draft_id: int) -> None: ...

    def should_continue(self, draft_id: int) -> tuple[bool, str]: ...
