"""
Broadcast helper for sending draft events to WebSocket channel groups.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from app.serializers import DraftEventSerializer, DraftSerializerForTournament

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
