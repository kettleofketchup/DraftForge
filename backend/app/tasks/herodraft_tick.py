"""Background task to broadcast tick updates during active drafts."""

import asyncio
import logging
import threading
from collections import namedtuple

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone

log = logging.getLogger(__name__)

# Thread-safe registry to prevent multiple threads per draft and enable stopping
_lock = threading.Lock()
_active_tick_tasks = {}  # draft_id -> TaskInfo(stop_event, thread)
TaskInfo = namedtuple("TaskInfo", ["stop_event", "thread"])


async def broadcast_tick(draft_id: int):
    """Broadcast current timing state to all connected clients."""
    from app.models import HeroDraft

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

        if draft.state != "drafting":
            return None

        current_round = draft.rounds.filter(state="active").first()
        if not current_round:
            return None

        teams = list(draft.draft_teams.all())
        team_a = teams[0] if teams else None
        team_b = teams[1] if len(teams) > 1 else None

        # Calculate grace time remaining
        now = timezone.now()
        if current_round.started_at:
            elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)
            grace_remaining = max(0, current_round.grace_time_ms - elapsed_ms)
        else:
            grace_remaining = current_round.grace_time_ms

        return {
            "type": "herodraft.tick",
            "current_round": current_round.round_number,
            "active_team_id": current_round.draft_team_id,
            "grace_time_remaining_ms": grace_remaining,
            "team_a_reserve_ms": team_a.reserve_time_remaining if team_a else 0,
            "team_b_reserve_ms": team_b.reserve_time_remaining if team_b else 0,
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

    from app.functions.herodraft import auto_random_pick
    from app.models import DraftTeam, HeroDraft

    @sync_to_async
    def check_and_auto_pick():
        # Use transaction with select_for_update to prevent race conditions
        with transaction.atomic():
            try:
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            except HeroDraft.DoesNotExist:
                return None

            if draft.state != "drafting":
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
                return auto_random_pick(draft, team)

            return None

    return await check_and_auto_pick()


async def run_tick_loop(draft_id: int, stop_event: threading.Event):
    """Run tick broadcasts every second while draft is active."""
    from app.models import HeroDraft

    @sync_to_async
    def is_draft_active():
        try:
            draft = HeroDraft.objects.get(id=draft_id)
            return draft.state == "drafting"
        except HeroDraft.DoesNotExist:
            return False

    while not stop_event.is_set() and await is_draft_active():
        await broadcast_tick(draft_id)
        await check_timeout(draft_id)
        await asyncio.sleep(1)


def start_tick_broadcaster(draft_id: int):
    """Start the tick broadcaster for a draft."""
    stop_event = threading.Event()

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_tick_loop(draft_id, stop_event))
        except Exception as e:
            log.error(f"Tick broadcaster error for draft {draft_id}: {e}")
        finally:
            loop.close()
            # Cleanup when loop ends (thread-safe)
            with _lock:
                _active_tick_tasks.pop(draft_id, None)

    # Check if already running and register (thread-safe)
    with _lock:
        if draft_id in _active_tick_tasks:
            log.debug(f"Tick broadcaster already running for draft {draft_id}")
            return

        thread = threading.Thread(target=run_in_thread, daemon=True)
        _active_tick_tasks[draft_id] = TaskInfo(stop_event, thread)

    # Start thread outside lock to avoid holding lock during thread startup
    thread.start()
    log.info(f"Started tick broadcaster for draft {draft_id}")


def stop_tick_broadcaster(draft_id: int):
    """Stop the tick broadcaster for a draft."""
    # Get task info (thread-safe)
    with _lock:
        task_info = _active_tick_tasks.get(draft_id)
        if task_info is None:
            return

    log.info(f"Stopping tick broadcaster for draft {draft_id}")

    # Signal the thread to stop
    task_info.stop_event.set()

    # Wait for thread to finish (outside lock to avoid deadlock)
    task_info.thread.join(timeout=2.0)

    # Clean up registry (thread-safe)
    # Note: thread's finally block may have already cleaned up
    with _lock:
        _active_tick_tasks.pop(draft_id, None)
