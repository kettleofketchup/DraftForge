"""Tick broadcaster. One thread + asyncio loop per active draft, Redis-locked.

Diagnostic events when ticks misbehave:
  tick_step_slow      — any sub-step >300ms
  tick_loop_stalled   — gap between consecutive ticks >1.5s (event-loop blocked)
  tick_slow           — whole iteration >1.5s
Tempo: herodraft.tick.iteration with child herodraft.tick.<step> spans.
"""

import asyncio
import atexit
import threading
import time
from collections import namedtuple

import redis
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import timezone
from opentelemetry import trace

from telemetry.logging import get_logger

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

TICK_STEP_SLOW_THRESHOLD_S = 0.3       # 30% of the 1s budget
TICK_GAP_STALL_THRESHOLD_S = 1.5       # expected gap is 1.0s
TICK_ITERATION_SLOW_THRESHOLD_S = 1.5  # backstop if no single step crossed

# Redis client for locking and connection tracking
_redis_client = None


def get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        redis_host = getattr(settings, "REDIS_HOST", "localhost")
        _redis_client = redis.Redis(
            host=redis_host, port=6379, db=2, decode_responses=True
        )
    return _redis_client


# Thread-safe registry for local cleanup
_lock = threading.Lock()
_active_tick_tasks = {}  # draft_id -> TaskInfo(stop_event, thread)
TaskInfo = namedtuple("TaskInfo", ["stop_event", "thread"])

# Connection tracking keys
CONN_COUNT_KEY = "herodraft:connections:{draft_id}"
LOCK_KEY = "herodraft:tick_lock:{draft_id}"
LOCK_TIMEOUT = 10  # Lock expires after 10 seconds (renewed each tick)


def increment_connection_count(draft_id: int) -> int:
    """Increment WebSocket connection count for a draft. Returns new count."""
    r = get_redis_client()
    key = CONN_COUNT_KEY.format(draft_id=draft_id)
    count = r.incr(key)
    r.expire(key, 300)  # Expire after 5 min of no activity
    log.debug(f"Draft {draft_id} connection count incremented to {count}")
    return count


def decrement_connection_count(draft_id: int) -> int:
    """Decrement WebSocket connection count for a draft. Returns new count."""
    r = get_redis_client()
    key = CONN_COUNT_KEY.format(draft_id=draft_id)
    count = r.decr(key)
    if count <= 0:
        r.delete(key)
        count = 0
    log.debug(f"Draft {draft_id} connection count decremented to {count}")
    return count


def get_connection_count(draft_id: int) -> int:
    """Get current WebSocket connection count for a draft."""
    r = get_redis_client()
    key = CONN_COUNT_KEY.format(draft_id=draft_id)
    count = r.get(key)
    return int(count) if count else 0


async def broadcast_tick(draft_id: int):
    """Broadcast timing anchors to all connected clients.

    Sends ANCHORS (timestamps + durations) not computed remainders.
    Clients render countdowns locally via requestAnimationFrame using
    `server_time` to compute clock offset. Decouples timer smoothness
    from broadcast cadence and eliminates the "everyone freezes for a
    few seconds" bug class.
    """
    from app.models import HeroDraft, HeroDraftState

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    room_group_name = f"herodraft_{draft_id}"

    @database_sync_to_async
    def get_tick_data():
        try:
            draft = HeroDraft.objects.get(id=draft_id)
        except HeroDraft.DoesNotExist:
            log.warning(
                "tick_skipped",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                reason="not_found",
            )
            return None

        now = timezone.now()

        if draft.state == HeroDraftState.RESUMING:
            # Include the round anchors too so the client can render the
            # frozen grace + reserve values that the timer will land on
            # when RESUMING completes — server has already pushed
            # round.started_at forward by pause_duration + 3s, so
            # `grace_time_ms - (resuming_until - round_started_at)`
            # equals the grace remaining at the moment of pause.
            current_round = draft.rounds.filter(state="active").first()
            teams = list(draft.draft_teams.all().order_by("id"))
            team_a = teams[0] if teams else None
            team_b = teams[1] if len(teams) > 1 else None
            return {
                "type": "herodraft.tick",
                "draft_state": draft.state,
                "server_time": now.isoformat(),
                "resuming_until": (
                    draft.resuming_until.isoformat() if draft.resuming_until else None
                ),
                "current_round": (
                    current_round.round_number - 1 if current_round else None
                ),
                "active_team_id": (
                    current_round.draft_team_id if current_round else None
                ),
                "round_started_at": (
                    current_round.started_at.isoformat()
                    if current_round and current_round.started_at
                    else None
                ),
                "round_grace_time_ms": (
                    current_round.grace_time_ms if current_round else None
                ),
                "team_a_id": team_a.id if team_a else None,
                "team_a_reserve_ms": team_a.reserve_time_remaining if team_a else None,
                "team_b_id": team_b.id if team_b else None,
                "team_b_reserve_ms": team_b.reserve_time_remaining if team_b else None,
            }

        if draft.state != HeroDraftState.DRAFTING:
            log.info(
                "tick_skipped",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                reason="wrong_state",
                draft_state=draft.state,
            )
            return None

        current_round = draft.rounds.filter(state="active").first()
        if not current_round:
            log.warning(
                "tick_skipped",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                reason="no_active_round",
            )
            return None

        # Deterministic team order by ID (matches frontend assumption)
        teams = list(draft.draft_teams.all().order_by("id"))
        team_a = teams[0] if teams else None
        team_b = teams[1] if len(teams) > 1 else None

        log.debug(
            "tick_broadcast",
            system="herodraft",
            subsystem="timer",
            draft_id=draft_id,
            round=current_round.round_number,
            server_time=now.isoformat(),
            round_started_at=(
                current_round.started_at.isoformat() if current_round.started_at else None
            ),
        )

        return {
            "type": "herodraft.tick",
            "draft_state": draft.state,
            # Clock anchor for client-side rAF countdown
            "server_time": now.isoformat(),
            # Round anchors — client computes elapsed/grace/reserve locally
            "current_round": current_round.round_number - 1,  # 0-indexed
            "active_team_id": current_round.draft_team_id,
            "round_started_at": (
                current_round.started_at.isoformat() if current_round.started_at else None
            ),
            "round_grace_time_ms": current_round.grace_time_ms,
            # DraftTeam.reserve_time_remaining — the team's cumulative
            # reserve in the DB. Stable between picks; server debits
            # `max(0, round_elapsed - grace)` at pick submission, so the
            # next round's broadcast carries the lower value forward.
            # The client subtracts the IN-ROUND consumption locally for
            # display on the active team only.
            "team_a_id": team_a.id if team_a else None,
            "team_a_reserve_ms": (
                team_a.reserve_time_remaining if team_a else None
            ),
            "team_b_id": team_b.id if team_b else None,
            "team_b_reserve_ms": (
                team_b.reserve_time_remaining if team_b else None
            ),
        }

    tick_data = await get_tick_data()
    if tick_data:
        try:
            await channel_layer.group_send(room_group_name, tick_data)
        except Exception as e:
            log.error(
                "tick_broadcast_failed",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                error=str(e),
            )


async def check_timeout(draft_id: int):
    """Check if current round has timed out and auto-pick if needed."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.functions.herodraft import auto_random_pick
    from app.models import DraftTeam, HeroDraft, HeroDraftState

    @database_sync_to_async
    def check_and_auto_pick():
        # Use transaction with select_for_update to prevent race conditions
        completed_round = None

        with transaction.atomic():
            try:
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            except HeroDraft.DoesNotExist:
                return None

            if draft.state != HeroDraftState.DRAFTING:
                return None

            current_round = (
                draft.rounds.select_for_update().filter(state="active").first()
            )
            if not current_round:
                return None

            now = timezone.now()
            if not current_round.started_at:
                return None

            elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)

            # Lock the team to ensure reserve_time_remaining is consistent
            team = DraftTeam.objects.select_for_update().get(
                id=current_round.draft_team_id
            )
            total_time = current_round.grace_time_ms + team.reserve_time_remaining

            if elapsed_ms >= total_time:
                # Time's up - auto pick
                log.info(
                    "timeout_auto_pick",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    round=current_round.round_number,
                    elapsed_ms=elapsed_ms,
                    total_time_ms=total_time,
                )
                completed_round = auto_random_pick(draft, team)

        # Broadcast AFTER transaction commits so clients see the updated state
        # Use broadcast_herodraft_state to avoid creating duplicate events
        # (submit_pick already creates the hero_selected event)
        if completed_round:
            try:
                # Re-fetch draft to get committed state with prefetched relations
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=draft_id)
                broadcast_herodraft_state(draft, "hero_selected")
                log.debug(
                    "timeout_auto_pick_broadcast",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                )
            except Exception as e:
                log.error(
                    "timeout_auto_pick_broadcast_failed",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    error=str(e),
                )

        return completed_round

    return await check_and_auto_pick()


async def check_resume_countdown(draft_id: int):
    """Check if RESUMING countdown is complete and transition to DRAFTING."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.models import HeroDraft, HeroDraftEvent, HeroDraftState

    @database_sync_to_async
    def check_and_resume():
        transitioned = False

        with transaction.atomic():
            try:
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            except HeroDraft.DoesNotExist:
                return False

            if draft.state != HeroDraftState.RESUMING:
                return False

            now = timezone.now()
            if not draft.resuming_until or now < draft.resuming_until:
                return False

            # Countdown complete - transition to DRAFTING
            draft.state = HeroDraftState.DRAFTING
            draft.resuming_until = None
            draft.save()
            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="draft_resumed",
                metadata={},
            )
            log.info(
                "draft_resumed",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
            )
            transitioned = True

        # Broadcast AFTER transaction commits
        if transitioned:
            try:
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=draft_id)
                broadcast_herodraft_state(draft, "draft_resumed")
                log.debug(f"Broadcast draft_resumed for draft {draft_id}")
            except Exception as e:
                log.error(
                    f"Failed to broadcast draft_resumed for draft {draft_id}: {e}"
                )

        return transitioned

    return await check_and_resume()


# Heartbeat key pattern (must match consumers.py)
CAPTAIN_HEARTBEAT_KEY = "herodraft:{draft_id}:captain:{user_id}:heartbeat"
HEARTBEAT_STALE_SECONDS = (
    9  # Consider stale if no heartbeat for 9 seconds (3 missed beats)
)


async def check_captain_heartbeats(draft_id: int):
    """Check if any captain's heartbeat is stale and trigger disconnect if so."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftState

    @database_sync_to_async
    def check_and_handle_stale():
        r = get_redis_client()
        now = time.time()
        stale_captain = None

        try:
            draft = HeroDraft.objects.prefetch_related(
                "draft_teams__tournament_team__captain"
            ).get(id=draft_id)
        except HeroDraft.DoesNotExist:
            return None

        # Only check during DRAFTING (not PAUSED, RESUMING, etc.)
        if draft.state != HeroDraftState.DRAFTING:
            return None

        # Check each captain's heartbeat
        for draft_team in draft.draft_teams.all():
            captain = draft_team.tournament_team.captain
            if not captain:
                continue

            heartbeat_key = CAPTAIN_HEARTBEAT_KEY.format(
                draft_id=draft_id, user_id=captain.id
            )
            last_heartbeat = r.get(heartbeat_key)

            if last_heartbeat is None:
                # No heartbeat recorded - captain may not have connected yet
                # or heartbeat expired (30s TTL)
                if draft_team.is_connected:
                    log.warning(
                        "heartbeat_missing",
                        system="herodraft",
                        subsystem="heartbeat",
                        draft_id=draft_id,
                        user_id=captain.id,
                        username=captain.username,
                        is_connected=True,
                        reason="no_heartbeat_key",
                    )
                    stale_captain = (draft_team, captain)
                    break
            else:
                heartbeat_age = now - float(last_heartbeat)
                if heartbeat_age > HEARTBEAT_STALE_SECONDS:
                    log.warning(
                        "heartbeat_stale",
                        system="herodraft",
                        subsystem="heartbeat",
                        draft_id=draft_id,
                        user_id=captain.id,
                        username=captain.username,
                        heartbeat_age_s=round(heartbeat_age, 1),
                        threshold_s=HEARTBEAT_STALE_SECONDS,
                    )
                    stale_captain = (draft_team, captain)
                    break

        if not stale_captain:
            return None

        draft_team, captain = stale_captain

        # Trigger disconnect handling
        with transaction.atomic():
            draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            if draft.state != HeroDraftState.DRAFTING:
                return None

            draft_team = DraftTeam.objects.select_for_update().get(id=draft_team.id)
            draft_team.is_connected = False
            draft_team.save()

            draft.state = HeroDraftState.PAUSED
            draft.paused_at = timezone.now()
            draft.save()

            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="captain_disconnected",
                draft_team=draft_team,
                metadata={
                    "user_id": captain.id,
                    "username": captain.username,
                    "reason": "heartbeat_stale",
                },
            )
            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="draft_paused",
                draft_team=draft_team,
                metadata={"reason": "heartbeat_stale"},
            )
            log.info(
                "heartbeat_triggered_pause",
                system="herodraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                user_id=captain.id,
                username=captain.username,
            )

        # Broadcast after transaction commits
        try:
            draft = HeroDraft.objects.prefetch_related(
                "draft_teams__tournament_team__captain",
                "draft_teams__tournament_team__members",
                "rounds",
            ).get(id=draft_id)
            broadcast_herodraft_state(draft, "draft_paused", draft_team=draft_team)
        except Exception as e:
            log.error(
                "heartbeat_broadcast_failed",
                system="herodraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                error=str(e),
            )

        return captain.username

    return await check_and_handle_stale()


def should_continue_ticking(draft_id: int, r: redis.Redis) -> tuple[bool, str]:
    """
    Check if tick loop should continue.

    Returns:
        tuple: (should_continue, reason_if_stopping)
    """
    from app.models import HeroDraft, HeroDraftState

    # Check draft state first - allow DRAFTING and RESUMING (countdown before resume)
    try:
        draft = HeroDraft.objects.get(id=draft_id)
        if draft.state not in (HeroDraftState.DRAFTING, HeroDraftState.RESUMING):
            return False, f"draft_state_{draft.state}"
    except HeroDraft.DoesNotExist:
        return False, "draft_not_found"

    # RESUMING countdown must complete regardless of connection count,
    # because admins resume via REST API and clients may reconnect after.
    if draft.state == HeroDraftState.RESUMING:
        return True, ""

    # For DRAFTING, stop if no WebSocket clients are connected
    conn_count = get_connection_count(draft_id)
    if conn_count <= 0:
        return False, "no_connections"

    return True, ""


async def run_tick_loop(draft_id: int, stop_event: threading.Event):
    """Run tick broadcasts every second while draft is active and has connections."""
    r = get_redis_client()
    lock_key = LOCK_KEY.format(draft_id=draft_id)

    @database_sync_to_async
    def check_continue():
        return should_continue_ticking(draft_id, r)

    @sync_to_async(thread_sensitive=False)
    def extend_lock():
        # Extend lock timeout to show we're still alive
        r.expire(lock_key, LOCK_TIMEOUT)

    log.info(
        "tick_loop_started", system="herodraft", subsystem="timer", draft_id=draft_id
    )
    tick_count = 0
    last_tick_start: float | None = None

    async def _timed_step(step_name: str, coro):
        """Span + duration log per sub-step. Warns past TICK_STEP_SLOW_THRESHOLD_S."""
        with tracer.start_as_current_span(
            f"herodraft.tick.{step_name}",
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
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_step=step_name,
                    tick_count=tick_count + 1,
                    duration_s=round(step_duration, 3),
                )

    while not stop_event.is_set():
        tick_start = time.time()

        # gap > expected = event loop was blocked outside per-step work
        if last_tick_start is not None:
            gap = tick_start - last_tick_start
            if gap > TICK_GAP_STALL_THRESHOLD_S:
                log.error(
                    "tick_loop_stalled",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_count=tick_count,
                    expected_gap_s=1.0,
                    actual_gap_s=round(gap, 3),
                    stall_s=round(gap - 1.0, 3),
                )

        with tracer.start_as_current_span(
            "herodraft.tick.iteration",
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
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    reason=reason,
                    tick_count=tick_count,
                )
                break

            await _timed_step("resume_countdown", check_resume_countdown(draft_id))
            await _timed_step("captain_heartbeats", check_captain_heartbeats(draft_id))
            await _timed_step("broadcast_tick", broadcast_tick(draft_id))
            await _timed_step("check_timeout", check_timeout(draft_id))
            await _timed_step("extend_lock", extend_lock())

            tick_duration = time.time() - tick_start
            tick_count += 1
            iter_span.set_attribute("tick.duration_s", round(tick_duration, 4))
            iter_span.set_attribute("tick.outcome", "completed")

            if tick_duration > TICK_ITERATION_SLOW_THRESHOLD_S:
                log.warning(
                    "tick_slow",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_count=tick_count,
                    duration_s=round(tick_duration, 2),
                )
            elif tick_count % 30 == 0:
                log.info(
                    "tick_loop_healthy",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    tick_count=tick_count,
                    duration_s=round(tick_duration, 3),
                )

        last_tick_start = tick_start
        # Sleep just enough to maintain a 1Hz cadence. Sleeping a flat 1s
        # would push the next tick out to `1s + work_duration`, which
        # made `tick_loop_stalled` over-report (it compares start-to-start
        # gaps against 1s expected). max(0, ...) absorbs a slow tick by
        # firing immediately on the next iteration to catch up.
        await asyncio.sleep(max(0.0, 1.0 - tick_duration))

    log.info(
        "tick_loop_ended",
        system="herodraft",
        subsystem="timer",
        draft_id=draft_id,
        tick_count=tick_count,
    )


def start_tick_broadcaster(draft_id: int) -> bool:
    """
    Start the tick broadcaster for a draft.

    Uses Redis distributed lock to ensure only one broadcaster runs
    across all Django instances.

    Returns:
        bool: True if broadcaster was started, False if already running elsewhere
    """
    r = get_redis_client()
    lock_key = LOCK_KEY.format(draft_id=draft_id)
    stop_event = threading.Event()

    # Try to acquire distributed lock (non-blocking)
    # SET NX = only set if not exists, EX = expire time
    acquired = r.set(lock_key, "locked", nx=True, ex=LOCK_TIMEOUT)

    if not acquired:
        log.debug(f"Tick broadcaster already running for draft {draft_id} (lock held)")
        return False

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_tick_loop(draft_id, stop_event))
        except Exception as e:
            log.error(f"Tick broadcaster error for draft {draft_id}: {e}")
        finally:
            loop.close()
            try:
                r.delete(lock_key)
            except Exception as e:
                log.debug(
                    "tick_lock_release_failed",
                    draft_id=draft_id,
                    phase="run_in_thread",
                    error=str(e),
                )
            with _lock:
                _active_tick_tasks.pop(draft_id, None)

    # Register locally for cleanup
    with _lock:
        if draft_id in _active_tick_tasks:
            # Race condition - another local thread started
            r.delete(lock_key)
            return False

        thread = threading.Thread(target=run_in_thread, daemon=True)
        _active_tick_tasks[draft_id] = TaskInfo(stop_event, thread)

    thread.start()
    log.info(f"Started tick broadcaster for draft {draft_id}")
    return True


def stop_tick_broadcaster(draft_id: int):
    """Stop the tick broadcaster for a draft."""
    r = get_redis_client()
    lock_key = LOCK_KEY.format(draft_id=draft_id)

    # Get local task info
    with _lock:
        task_info = _active_tick_tasks.get(draft_id)

    if task_info:
        log.info(f"Stopping tick broadcaster for draft {draft_id}")
        task_info.stop_event.set()
        task_info.thread.join(timeout=2.0)

    try:
        r.delete(lock_key)
    except Exception as e:
        log.debug(
            "tick_lock_release_failed",
            draft_id=draft_id,
            phase="stop_tick_broadcaster",
            error=str(e),
        )

    with _lock:
        _active_tick_tasks.pop(draft_id, None)


def stop_all_broadcasters():
    """Stop all active tick broadcasters. Called on shutdown."""
    with _lock:
        draft_ids = list(_active_tick_tasks.keys())

    for draft_id in draft_ids:
        stop_tick_broadcaster(draft_id)

    log.info(f"Stopped {len(draft_ids)} tick broadcasters on shutdown")


# Register cleanup on process exit
atexit.register(stop_all_broadcasters)
