"""Shared draft tick runner, parameterised by a Redis key/span prefix.

herodraft_tick.py binds this module to "herodraft". Drivers supply the
draft-specific steps via TickDriver.

Diagnostic events when ticks misbehave:
  tick_step_slow      - any sub-step >300ms
  tick_loop_stalled   - gap between consecutive ticks >1.5s (event-loop blocked)
  tick_slow           - whole iteration >1.5s
"""

import asyncio
import atexit
import contextvars
import threading
import time
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, NamedTuple, Protocol, runtime_checkable

import redis
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.conf import settings
from opentelemetry import trace

from telemetry.logging import get_logger

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

TICK_STEP_SLOW_THRESHOLD_S: float = 0.3
TICK_GAP_STALL_THRESHOLD_S: float = 1.5
TICK_ITERATION_SLOW_THRESHOLD_S: float = 1.5

LOCK_TIMEOUT: int = 10
CONN_COUNT_TTL_SECONDS: int = 300
HEARTBEAT_INTERVAL_SECONDS: int = 3
HEARTBEAT_STALE_SECONDS: int = 9
HEARTBEAT_TTL: int = 30
CAPTAIN_CHANNEL_TTL: int = 300
CLIENT_PICK_TIME_MAX_AGE_S: float = 2.0

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        redis_host = getattr(settings, "REDIS_HOST", "localhost")
        _redis_client = redis.Redis(
            host=redis_host, port=6379, db=2, decode_responses=True
        )
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


_lock = threading.Lock()
_registries: dict[str, dict[int, TaskInfo]] = {}


def registry_for(prefix: str) -> dict[int, TaskInfo]:
    return _registries.setdefault(prefix, {})


async def run_tick_loop(
    driver: TickDriver, draft_id: int, stop_event: threading.Event
) -> None:
    """Run tick broadcasts every second while draft is active and has connections."""
    r = get_redis_client()
    key = lock_key(driver.prefix, draft_id)

    @database_sync_to_async
    def check_continue() -> tuple[bool, str]:
        return driver.should_continue(draft_id)

    @sync_to_async(thread_sensitive=False)
    def extend_lock() -> None:
        r.expire(key, LOCK_TIMEOUT)

    log.info(
        "tick_loop_started", system=driver.system, subsystem="timer", draft_id=draft_id
    )
    tick_count = 0
    last_tick_start: float | None = None

    async def _timed_step(step_name: str, coro: Coroutine[Any, Any, None]) -> None:
        """Span + duration log per sub-step. Warns past TICK_STEP_SLOW_THRESHOLD_S."""
        with tracer.start_as_current_span(
            f"{driver.prefix}.tick.{step_name}",
            attributes={
                "ws.draft_id": draft_id,
                "tick.step": step_name,
                "tick.iteration": tick_count + 1,
            },
        ) as span:
            step_start = time.time()
            await coro
            step_duration = time.time() - step_start
            span.set_attribute("tick.step_duration_s", round(step_duration, 4))
            if step_duration > TICK_STEP_SLOW_THRESHOLD_S:
                log.warning(
                    "tick_step_slow",
                    system=driver.system,
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_step=step_name,
                    tick_count=tick_count + 1,
                    duration_s=round(step_duration, 3),
                )

    while not stop_event.is_set():
        tick_start = time.time()

        if last_tick_start is not None:
            gap = tick_start - last_tick_start
            if gap > TICK_GAP_STALL_THRESHOLD_S:
                log.error(
                    "tick_loop_stalled",
                    system=driver.system,
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_count=tick_count,
                    expected_gap_s=1.0,
                    actual_gap_s=round(gap, 3),
                    stall_s=round(gap - 1.0, 3),
                )

        with tracer.start_as_current_span(
            f"{driver.prefix}.tick.iteration",
            attributes={
                "ws.draft_id": draft_id,
                "tick.iteration": tick_count + 1,
            },
        ) as iter_span:
            should_continue, reason = await check_continue()
            if not should_continue:
                iter_span.set_attribute("tick.outcome", "stopping")
                iter_span.set_attribute("tick.stop_reason", reason)
                log.info(
                    "tick_loop_stopping",
                    system=driver.system,
                    subsystem="timer",
                    draft_id=draft_id,
                    reason=reason,
                    tick_count=tick_count,
                )
                break

            await _timed_step(
                "resume_countdown", driver.check_resume_countdown(draft_id)
            )
            await _timed_step(
                "captain_heartbeats", driver.check_captain_heartbeats(draft_id)
            )
            await _timed_step("broadcast_tick", driver.broadcast_tick(draft_id))
            await _timed_step("check_timeout", driver.check_timeout(draft_id))
            await _timed_step("extend_lock", extend_lock())

            tick_duration = time.time() - tick_start
            tick_count += 1
            iter_span.set_attribute("tick.duration_s", round(tick_duration, 4))
            iter_span.set_attribute("tick.outcome", "completed")

            if tick_duration > TICK_ITERATION_SLOW_THRESHOLD_S:
                log.warning(
                    "tick_slow",
                    system=driver.system,
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_count=tick_count,
                    duration_s=round(tick_duration, 2),
                )
            elif tick_count % 30 == 0:
                log.info(
                    "tick_loop_healthy",
                    system=driver.system,
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_count=tick_count,
                    duration_s=round(tick_duration, 3),
                )

        last_tick_start = tick_start
        # Hold a 1Hz start-to-start cadence; a slow tick fires the next immediately.
        await asyncio.sleep(max(0.0, 1.0 - tick_duration))

    log.info(
        "tick_loop_ended",
        system=driver.system,
        subsystem="timer",
        draft_id=draft_id,
        tick_count=tick_count,
    )


def start_tick_broadcaster(driver: TickDriver, draft_id: int) -> bool:
    """Start the tick broadcaster for a draft under a Redis lock.

    Returns True if started, False if already running (here or on another instance).
    """
    r = get_redis_client()
    key = lock_key(driver.prefix, draft_id)
    reg = registry_for(driver.prefix)
    stop_event = threading.Event()

    acquired = r.set(key, "locked", nx=True, ex=LOCK_TIMEOUT)

    if not acquired:
        log.debug(
            "tick_broadcaster_already_running",
            system=driver.system,
            subsystem="timer",
            draft_id=draft_id,
            reason="lock_held",
        )
        return False

    def run_in_thread() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_tick_loop(driver, draft_id, stop_event))
        except Exception as e:
            log.error(
                "tick_broadcaster_error",
                system=driver.system,
                subsystem="timer",
                draft_id=draft_id,
                error=str(e),
            )
        finally:
            loop.close()
            try:
                r.delete(key)
            except Exception as e:
                log.debug(
                    "tick_lock_release_failed",
                    system=driver.system,
                    subsystem="timer",
                    draft_id=draft_id,
                    phase="run_in_thread",
                    error=str(e),
                )
            with _lock:
                reg.pop(draft_id, None)

    with _lock:
        if draft_id in reg:
            r.delete(key)
            return False

        # A fresh context: on_commit starters may hold request-scoped ContextVars.
        thread = threading.Thread(
            target=contextvars.Context().run, args=(run_in_thread,), daemon=True
        )
        reg[draft_id] = TaskInfo(stop_event, thread)

    try:
        thread.start()
    except Exception:
        with _lock:
            reg.pop(draft_id, None)
        r.delete(key)
        raise
    log.info(
        "tick_broadcaster_started",
        system=driver.system,
        subsystem="timer",
        draft_id=draft_id,
    )
    return True


def stop_tick_broadcaster(prefix: str, draft_id: int) -> None:
    """Stop the tick broadcaster for a draft."""
    r = get_redis_client()
    key = lock_key(prefix, draft_id)
    reg = registry_for(prefix)

    with _lock:
        task_info = reg.get(draft_id)

    if task_info:
        log.info(
            "tick_broadcaster_stopping",
            system=prefix,
            subsystem="timer",
            draft_id=draft_id,
        )
        task_info.stop_event.set()
        task_info.thread.join(timeout=2.0)

    try:
        r.delete(key)
    except Exception as e:
        log.debug(
            "tick_lock_release_failed",
            system=prefix,
            subsystem="timer",
            draft_id=draft_id,
            phase="stop_tick_broadcaster",
            error=str(e),
        )

    with _lock:
        reg.pop(draft_id, None)


def stop_all_broadcasters() -> None:
    """Stop every active tick broadcaster across all prefixes. Called on shutdown."""
    with _lock:
        targets = [
            (prefix, draft_id)
            for prefix, reg in _registries.items()
            for draft_id in reg
        ]

    for prefix, draft_id in targets:
        stop_tick_broadcaster(prefix, draft_id)

    log.info(
        "tick_broadcasters_shutdown",
        system="websocket",
        subsystem="timer",
        count=len(targets),
    )


atexit.register(stop_all_broadcasters)


def evaluate_client_pick_time(
    server_now: datetime,
    client_picked_at: datetime | None,
    draft_id: int,
    *,
    system: str,
    subsystem: str,
) -> tuple[datetime, str, int | None]:
    """Decide whether to trust the client's pick time + log any weirdness.

    Returns (effective_time, source, age_ms) where:
        effective_time: datetime to compute elapsed from
        source: "client" if we trusted it, "server_now" otherwise
        age_ms: client→server delta in ms (or None when no client_picked_at)
    """
    if not client_picked_at:
        return server_now, "server_now", None

    # Subtracting a naive datetime from a tz-aware one raises TypeError.
    # The view layer also filters these out; this is a defense-in-depth
    # guard for tests or future direct callers.
    if client_picked_at.tzinfo is None:
        log.warning(
            "pick_time_naive_datetime",
            system=system,
            subsystem=subsystem,
            draft_id=draft_id,
        )
        return server_now, "server_now", None

    age_s = (server_now - client_picked_at).total_seconds()
    age_ms = int(age_s * 1000)

    if age_s < 0:
        # Client clock is in the future relative to server. Most often
        # clock skew (laptop with bad NTP), occasionally a hostile client
        # trying to win back time. Falls through to server time.
        log.warning(
            "pick_time_in_future",
            system=system,
            subsystem=subsystem,
            draft_id=draft_id,
            future_by_ms=-age_ms,
        )
        return server_now, "server_now", age_ms

    if age_s > CLIENT_PICK_TIME_MAX_AGE_S:
        # Pick payload arrived more than the sanity window after the
        # client sent it. Network was slow or the client buffered the
        # request. We discard the client timestamp to prevent abuse;
        # this means the captain eats the network latency on this pick.
        log.warning(
            "pick_time_too_old",
            system=system,
            subsystem=subsystem,
            draft_id=draft_id,
            age_ms=age_ms,
            max_age_ms=int(CLIENT_PICK_TIME_MAX_AGE_S * 1000),
        )
        return server_now, "server_now", age_ms

    return client_picked_at, "client", age_ms
