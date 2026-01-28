"""
Broadcast helper for sending draft events to WebSocket channel groups.

All broadcast functions support an optional `use_on_commit=True` parameter (default)
that wraps the actual send in `transaction.on_commit()` to ensure messages are only
sent after the current database transaction commits. This prevents clients from
receiving events before the data they reference is persisted.

Set `use_on_commit=False` when broadcasting outside of a transaction context
(e.g., from background tasks or signals that run after commits).
"""

import logging
from functools import partial

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import connection

from app.serializers import (
    DraftEventSerializer,
    DraftSerializerForTournament,
    DraftTeamSerializerFull,
    HeroDraftSerializer,
)

log = logging.getLogger(__name__)


def _run_on_commit_or_now(func, use_on_commit=True):
    """
    Execute a function either immediately or after the current transaction commits.

    Args:
        func: The function to execute (should take no arguments)
        use_on_commit: If True, wrap in transaction.on_commit(). If False, run immediately.
    """
    if use_on_commit:
        connection.on_commit(func)
    else:
        func()


def get_next_sequence(channel_name: str) -> int:
    """
    Get the next sequence number for a channel group.
    Uses Redis INCR for atomic increment.

    Args:
        channel_name: The channel group name (e.g., "draft_123", "herodraft_456")

    Returns:
        The next sequence number (starts at 1)
    """
    key = f"ws_seq:{channel_name}"
    try:
        # Use Redis INCR for atomic increment
        # If key doesn't exist, INCR creates it with value 1
        seq = cache.incr(key)
        # Set TTL of 24 hours on first creation
        if seq == 1:
            cache.expire(key, 86400)
        return seq
    except Exception as e:
        log.warning(f"Failed to get sequence number for {channel_name}: {e}")
        # Return 0 to indicate sequence unavailable - clients should handle gracefully
        return 0


def broadcast_event(event, include_draft_state=True, use_on_commit=True):
    """
    Broadcast a DraftEvent to both draft-specific and tournament channel groups.

    Args:
        event: DraftEvent instance to broadcast
        include_draft_state: If True, include the full draft state in the broadcast.
            This allows clients to update their state without making additional API calls.
        use_on_commit: If True (default), defer broadcast until transaction commits.
            Set to False when calling from outside a transaction.

    Note:
        This function gracefully handles connection errors (e.g., Redis unavailable)
        to allow draft operations to proceed even without real-time broadcasting.
    """
    # Capture event data immediately (before potential transaction rollback)
    event_id = event.id
    event_type = event.event_type
    draft_id = event.draft_id
    tournament_id = event.draft.tournament_id
    payload = DraftEventSerializer(event).data

    # Capture draft state immediately if requested
    draft_state = None
    if include_draft_state:
        try:
            event.draft.refresh_from_db()
            draft_state = DraftSerializerForTournament(event.draft).data
        except Exception as e:
            log.warning(f"Failed to serialize draft state: {e}")

    def _do_broadcast():
        channel_layer = get_channel_layer()
        if channel_layer is None:
            log.warning("No channel layer configured, skipping broadcast")
            return

        try:
            # Get sequence numbers for both channels
            draft_channel = f"draft_{draft_id}"
            tournament_channel = f"tournament_{tournament_id}"
            draft_seq = get_next_sequence(draft_channel)
            tournament_seq = get_next_sequence(tournament_channel)

            # Build message with sequence number
            base_message = {
                "type": "draft.event",
                "payload": payload,
            }
            if draft_state:
                base_message["draft_state"] = draft_state

            # Send to draft-specific channel with its sequence
            draft_message = {**base_message, "sequence": draft_seq}
            async_to_sync(channel_layer.group_send)(draft_channel, draft_message)

            # Send to tournament channel with its sequence
            tournament_message = {**base_message, "sequence": tournament_seq}
            async_to_sync(channel_layer.group_send)(
                tournament_channel, tournament_message
            )

            log.debug(
                f"Broadcast {event_type} to {draft_channel} (seq={draft_seq}) "
                f"and {tournament_channel} (seq={tournament_seq})"
                + (" (with draft state)" if draft_state else "")
            )
        except Exception as e:
            # Log the error but don't fail the draft operation
            log.warning(
                f"Failed to broadcast {event_type} to channels: {e}. "
                "WebSocket clients will not receive real-time updates for this event."
            )

    _run_on_commit_or_now(_do_broadcast, use_on_commit)


def broadcast_herodraft_event(
    draft, event_type: str, draft_team=None, metadata=None, use_on_commit=True
):
    """
    Broadcast a HeroDraft event to WebSocket consumers.

    Args:
        draft: HeroDraft instance
        event_type: Type of event (e.g., "captain_ready", "hero_selected")
        draft_team: DraftTeam instance (optional)
        metadata: Additional event metadata (optional)
        use_on_commit: If True (default), defer broadcast until transaction commits.
            Set to False when calling from outside a transaction.
    """
    from app.models import HeroDraftEvent

    # Create event record immediately (this is part of the transaction)
    event = HeroDraftEvent.objects.create(
        draft=draft,
        event_type=event_type,
        draft_team=draft_team,
        metadata=metadata or {},
    )

    # Capture data immediately before potential transaction rollback
    draft_id = draft.id
    event_id = event.id
    timestamp = event.created_at.isoformat()
    draft_team_data = DraftTeamSerializerFull(draft_team).data if draft_team else None

    # Build draft state immediately
    draft_state = None
    try:
        from app.models import HeroDraft

        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft_id)
        draft_state = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(f"Failed to serialize herodraft state: {e}")

    def _do_broadcast():
        channel_layer = get_channel_layer()
        if channel_layer is None:
            log.warning("No channel layer configured, skipping herodraft broadcast")
            return

        # Build payload
        payload = {
            "type": "herodraft.event",
            "event_type": event_type,
            "event_id": event_id,
            "draft_team": draft_team_data,
            "metadata": metadata or {},
            "timestamp": timestamp,
        }
        if draft_state:
            payload["draft_state"] = draft_state

        # Send to channel group
        room_group_name = f"herodraft_{draft_id}"

        try:
            # Add sequence number
            seq = get_next_sequence(room_group_name)
            payload["sequence"] = seq
            async_to_sync(channel_layer.group_send)(room_group_name, payload)
            log.debug(
                f"Broadcast herodraft {event_type} to {room_group_name} (seq={seq})"
            )
        except Exception as e:
            log.warning(
                f"Failed to broadcast herodraft {event_type} to channels: {e}. "
                "WebSocket clients will not receive real-time updates for this event."
            )

    _run_on_commit_or_now(_do_broadcast, use_on_commit)


def broadcast_herodraft_state(
    draft, event_type: str, metadata=None, use_on_commit=True
):
    """
    Broadcast the current HeroDraft state to WebSocket consumers.

    Used for state changes like pause/resume where the event is already created.
    This avoids creating duplicate events.

    Args:
        draft: HeroDraft instance (should be refreshed from DB)
        event_type: Type of event for logging (e.g., "draft_paused", "draft_resumed")
        metadata: Additional event metadata (optional, e.g., countdown_seconds)
        use_on_commit: If True (default), defer broadcast until transaction commits.
            Set to False when calling from outside a transaction.
    """
    # Capture draft ID and state immediately
    draft_id = draft.id

    # Build draft state immediately
    draft_state = None
    try:
        from app.models import HeroDraft

        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft_id)
        draft_state = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(f"Failed to serialize herodraft state: {e}")
        return  # Don't broadcast without state

    def _do_broadcast():
        channel_layer = get_channel_layer()
        if channel_layer is None:
            log.warning(
                "No channel layer configured, skipping herodraft state broadcast"
            )
            return

        # Build payload with current state
        payload = {
            "type": "herodraft.event",
            "event_type": event_type,
        }

        if metadata:
            payload["metadata"] = metadata
        if draft_state:
            payload["draft_state"] = draft_state

        # Send to channel group
        room_group_name = f"herodraft_{draft_id}"

        try:
            # Add sequence number
            seq = get_next_sequence(room_group_name)
            payload["sequence"] = seq
            async_to_sync(channel_layer.group_send)(room_group_name, payload)
            log.debug(
                f"Broadcast herodraft state ({event_type}) to {room_group_name} (seq={seq})"
            )
        except Exception as e:
            log.warning(
                f"Failed to broadcast herodraft state to channels: {e}. "
                "WebSocket clients will not receive real-time updates."
            )

    _run_on_commit_or_now(_do_broadcast, use_on_commit)
