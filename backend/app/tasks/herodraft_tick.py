"""Background task to broadcast tick updates during active drafts."""

import asyncio
import logging
import threading

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone

log = logging.getLogger(__name__)

# Thread registry to prevent multiple threads per draft and enable stopping
_active_tick_tasks = {}  # draft_id -> threading.Event (stop signal)


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
        await asyncio.sleep(1)


def start_tick_broadcaster(draft_id: int):
    """Start the tick broadcaster for a draft."""
    # Check if already running
    if draft_id in _active_tick_tasks:
        log.debug(f"Tick broadcaster already running for draft {draft_id}")
        return

    stop_event = threading.Event()
    _active_tick_tasks[draft_id] = stop_event

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_tick_loop(draft_id, stop_event))
        except Exception as e:
            log.error(f"Tick broadcaster error for draft {draft_id}: {e}")
        finally:
            loop.close()
            # Cleanup when loop ends
            if draft_id in _active_tick_tasks:
                del _active_tick_tasks[draft_id]

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    log.info(f"Started tick broadcaster for draft {draft_id}")


def stop_tick_broadcaster(draft_id: int):
    """Stop the tick broadcaster for a draft."""
    if draft_id in _active_tick_tasks:
        log.info(f"Stopping tick broadcaster for draft {draft_id}")
        _active_tick_tasks[draft_id].set()  # Signal stop
        del _active_tick_tasks[draft_id]
