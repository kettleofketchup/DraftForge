"""
Broadcast helper for sending draft events to WebSocket channel groups.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from app.serializers import (
    DraftEventSerializer,
    DraftSerializerForTournament,
    DraftTeamSerializerFull,
    HeroDraftSerializer,
)

log = logging.getLogger(__name__)


def broadcast_event(event, include_draft_state=True):
    """
    Broadcast a DraftEvent to both draft-specific and tournament channel groups.

    Args:
        event: DraftEvent instance to broadcast
        include_draft_state: If True, include the full draft state in the broadcast.
            This allows clients to update their state without making additional API calls.

    Note:
        This function gracefully handles connection errors (e.g., Redis unavailable)
        to allow draft operations to proceed even without real-time broadcasting.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning("No channel layer configured, skipping broadcast")
        return

    payload = DraftEventSerializer(event).data
    tournament_id = event.draft.tournament_id

    # Include the full draft state so clients can update without additional API calls
    draft_state = None
    if include_draft_state:
        try:
            # Refresh the draft from DB to get the latest state
            event.draft.refresh_from_db()
            draft_state = DraftSerializerForTournament(event.draft).data
        except Exception as e:
            log.warning(f"Failed to serialize draft state: {e}")

    try:
        message = {
            "type": "draft.event",
            "payload": payload,
        }
        if draft_state:
            message["draft_state"] = draft_state

        # Send to draft-specific channel
        async_to_sync(channel_layer.group_send)(
            f"draft_{event.draft_id}",
            message,
        )

        # Send to tournament channel
        async_to_sync(channel_layer.group_send)(
            f"tournament_{tournament_id}",
            message,
        )

        log.debug(
            f"Broadcast {event.event_type} to draft_{event.draft_id} and tournament_{tournament_id}"
            + (" (with draft state)" if draft_state else "")
        )
    except Exception as e:
        # Log the error but don't fail the draft operation
        log.warning(
            f"Failed to broadcast {event.event_type} to channels: {e}. "
            "WebSocket clients will not receive real-time updates for this event."
        )


def broadcast_herodraft_event(draft, event_type: str, draft_team=None, metadata=None):
    """
    Broadcast a HeroDraft event to WebSocket consumers.

    Args:
        draft: HeroDraft instance
        event_type: Type of event (e.g., "captain_ready", "hero_selected")
        draft_team: DraftTeam instance (optional)
        metadata: Additional event metadata (optional)
    """
    from app.models import HeroDraftEvent

    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning("No channel layer configured, skipping herodraft broadcast")
        return

    # Create event record (if not already created by the view)
    event = HeroDraftEvent.objects.create(
        draft=draft,
        event_type=event_type,
        draft_team=draft_team,
        metadata=metadata or {},
    )

    # Build payload
    payload = {
        "type": "herodraft.event",
        "event_type": event_type,
        "event_id": event.id,
        "draft_team": DraftTeamSerializerFull(draft_team).data if draft_team else None,
        "timestamp": event.created_at.isoformat(),
    }

    # Include full draft state
    try:
        draft.refresh_from_db()
        payload["draft_state"] = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(f"Failed to serialize herodraft state: {e}")

    # Send to channel group
    room_group_name = f"herodraft_{draft.id}"

    try:
        async_to_sync(channel_layer.group_send)(room_group_name, payload)
        log.debug(f"Broadcast herodraft {event_type} to {room_group_name}")
    except Exception as e:
        log.warning(
            f"Failed to broadcast herodraft {event_type} to channels: {e}. "
            "WebSocket clients will not receive real-time updates for this event."
        )
