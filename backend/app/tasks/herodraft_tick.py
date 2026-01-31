"""Background task to broadcast tick updates during active drafts.

Uses Redis distributed locking to prevent duplicate broadcasters across
multiple Django instances, and connection tracking to stop when no
WebSocket clients are connected.
"""

import asyncio
import atexit
import logging
import threading
import time
from collections import namedtuple

import redis
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)

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
    """Broadcast current timing state to all connected clients."""
    from app.models import HeroDraft, HeroDraftState

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    room_group_name = f"herodraft_{draft_id}"

    @sync_to_async
    def get_tick_data():
        try:
            draft = HeroDraft.objects.get(id=draft_id)
        except HeroDraft.DoesNotExist:
            return None

        # Handle RESUMING state - broadcast countdown remaining
        if draft.state == HeroDraftState.RESUMING:
            now = timezone.now()
            countdown_remaining_ms = 0
            if draft.resuming_until:
                remaining = (draft.resuming_until - now).total_seconds() * 1000
                countdown_remaining_ms = max(0, int(remaining))

            return {
                "type": "herodraft.tick",
                "draft_state": draft.state,
                "countdown_remaining_ms": countdown_remaining_ms,
            }

        if draft.state != HeroDraftState.DRAFTING:
            return None

        current_round = draft.rounds.filter(state="active").first()
        if not current_round:
            return None

        # Use explicit ordering by ID for deterministic team order
        teams = list(draft.draft_teams.all().order_by("id"))
        team_a = teams[0] if teams else None
        team_b = teams[1] if len(teams) > 1 else None

        # Calculate grace time remaining and reserve time being consumed
        now = timezone.now()
        elapsed_ms = 0
        grace_remaining = current_round.grace_time_ms

        if current_round.started_at:
            elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)
            grace_remaining = max(0, current_round.grace_time_ms - elapsed_ms)

        # Calculate how much reserve time has been consumed (time past grace period)
        reserve_consumed_ms = max(0, elapsed_ms - current_round.grace_time_ms)

        # Calculate real-time reserve time for each team
        # Only the active team's reserve is being consumed
        active_team_id = current_round.draft_team_id
        team_a_reserve = team_a.reserve_time_remaining if team_a else 0
        team_b_reserve = team_b.reserve_time_remaining if team_b else 0

        # Calculate remaining reserve for the active team (for broadcast only)
        # Database is updated when pick is submitted in herodraft.py
        if team_a and team_a.id == active_team_id:
            team_a_reserve = max(0, team_a_reserve - reserve_consumed_ms)
        elif team_b and team_b.id == active_team_id:
            team_b_reserve = max(0, team_b_reserve - reserve_consumed_ms)

        log.debug(
            f"Tick draft {draft_id}: round={current_round.round_number}, "
            f"elapsed={elapsed_ms}ms, grace_remaining={grace_remaining}ms, "
            f"reserve_consumed={reserve_consumed_ms}ms, "
            f"team_a_reserve={team_a_reserve}ms, team_b_reserve={team_b_reserve}ms"
        )

        return {
            "type": "herodraft.tick",
            "current_round": current_round.round_number
            - 1,  # 0-indexed to match state serializer
            "active_team_id": active_team_id,
            "grace_time_remaining_ms": grace_remaining,
            # Include team IDs so frontend can match reserve times correctly
            "team_a_id": team_a.id if team_a else None,
            "team_a_reserve_ms": team_a_reserve,
            "team_b_id": team_b.id if team_b else None,
            "team_b_reserve_ms": team_b_reserve,
            "draft_state": draft.state,
        }

    tick_data = await get_tick_data()
    if tick_data:
        try:
            await channel_layer.group_send(room_group_name, tick_data)
        except Exception as e:
            log.warning(f"Failed to broadcast tick for draft {draft_id}: {e}")


async def check_timeout(draft_id: int):
    """Check if current round has timed out and auto-pick if needed."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.functions.herodraft import auto_random_pick
    from app.models import DraftTeam, HeroDraft, HeroDraftState

    @sync_to_async
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
                    f"Timeout reached for draft {draft_id}, round {current_round.round_number}"
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
                log.debug(f"Broadcast auto-pick state for draft {draft_id}")
            except Exception as e:
                log.error(f"Failed to broadcast auto-pick for draft {draft_id}: {e}")

        return completed_round

    return await check_and_auto_pick()


async def check_resume_countdown(draft_id: int):
    """Check if RESUMING countdown is complete and transition to DRAFTING."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.models import HeroDraft, HeroDraftEvent, HeroDraftState

    @sync_to_async
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
            log.info(f"HeroDraft {draft_id} resumed after countdown")
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

    @sync_to_async
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
                        f"Captain {captain.username} has no heartbeat but marked connected - "
                        f"treating as stale for draft {draft_id}"
                    )
                    stale_captain = (draft_team, captain)
                    break
            else:
                heartbeat_age = now - float(last_heartbeat)
                if heartbeat_age > HEARTBEAT_STALE_SECONDS:
                    log.warning(
                        f"Captain {captain.username} heartbeat stale ({heartbeat_age:.1f}s) "
                        f"for draft {draft_id}"
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
                f"HeroDraft {draft_id} paused: captain {captain.username} heartbeat stale"
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
            log.error(f"Failed to broadcast draft_paused for draft {draft_id}: {e}")

        return captain.username

    return await check_and_handle_stale()


def should_continue_ticking(draft_id: int, r: redis.Redis) -> tuple[bool, str]:
    """
    Check if tick loop should continue.

    Returns:
        tuple: (should_continue, reason_if_stopping)
    """
    from app.models import HeroDraft, HeroDraftState

    # Check connection count
    conn_count = get_connection_count(draft_id)
    if conn_count <= 0:
        return False, "no_connections"

    # Check draft state - allow DRAFTING and RESUMING (countdown before resume)
    try:
        draft = HeroDraft.objects.get(id=draft_id)
        if draft.state not in (HeroDraftState.DRAFTING, HeroDraftState.RESUMING):
            return False, f"draft_state_{draft.state}"
    except HeroDraft.DoesNotExist:
        return False, "draft_not_found"

    return True, ""


async def run_tick_loop(draft_id: int, stop_event: threading.Event):
    """Run tick broadcasts every second while draft is active and has connections."""
    r = get_redis_client()
    lock_key = LOCK_KEY.format(draft_id=draft_id)

    @sync_to_async
    def check_continue():
        return should_continue_ticking(draft_id, r)

    @sync_to_async
    def extend_lock():
        # Extend lock timeout to show we're still alive
        r.expire(lock_key, LOCK_TIMEOUT)

    log.info(f"Tick loop started for draft {draft_id}")

    while not stop_event.is_set():
        should_continue, reason = await check_continue()
        if not should_continue:
            log.info(f"Stopping tick loop for draft {draft_id}: {reason}")
            break

        # Check if RESUMING countdown is complete first
        await check_resume_countdown(draft_id)
        # Check for stale captain heartbeats (zombie connections)
        await check_captain_heartbeats(draft_id)
        await broadcast_tick(draft_id)
        await check_timeout(draft_id)
        await extend_lock()
        await asyncio.sleep(1)

    log.info(f"Tick loop ended for draft {draft_id}")


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
            # Release lock and cleanup
            try:
                r.delete(lock_key)
            except Exception:
                pass
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

    # Release lock (in case local thread didn't clean up)
    try:
        r.delete(lock_key)
    except Exception:
        pass

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
