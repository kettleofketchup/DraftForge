"""Broadcast helpers for sending hero draft events to WebSocket channel groups."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from draft.models import DraftTeam, HeroDraft, HeroDraftEvent
from draft.serializers.hero import DraftTeamSerializerFull, HeroDraftSerializer
from draft.services.hero_state import herodraft_state_queryset
from telemetry.logging import get_logger

log = get_logger(__name__)


def broadcast_herodraft_event(
    draft: HeroDraft,
    event_type: str,
    draft_team: DraftTeam | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Broadcast a HeroDraft event to WebSocket consumers.

    Args:
        draft: HeroDraft instance
        event_type: Type of event (e.g., "captain_ready", "hero_selected")
        draft_team: DraftTeam instance (optional)
        metadata: Additional event metadata (optional)
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "broadcast_skipped",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            reason="no_channel_layer",
            draft_id=draft.id,
        )
        return

    event = HeroDraftEvent.objects.create(
        draft=draft,
        event_type=event_type,
        draft_team=draft_team,
        metadata=metadata or {},
    )

    payload = {
        "type": "herodraft.event",
        "event_type": event_type,
        "event_id": event.id,
        "draft_team": DraftTeamSerializerFull(draft_team).data if draft_team else None,
        "metadata": metadata or {},  # Include metadata for hero_id, action_type etc
        "timestamp": event.created_at.isoformat(),
    }

    try:
        draft = herodraft_state_queryset().get(id=draft.id)
        payload["draft_state"] = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(
            "broadcast_serialize_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            draft_id=draft.id,
            error=str(e),
        )

    room_group_name = f"herodraft_{draft.id}"

    try:
        async_to_sync(channel_layer.group_send)(room_group_name, payload)
        log.debug(
            "broadcast_sent",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            event_type=event_type,
            draft_id=draft.id,
            event_id=event.id,
        )
    except Exception as e:
        log.warning(
            "broadcast_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            event_type=event_type,
            draft_id=draft.id,
            error=str(e),
        )


def broadcast_herodraft_state(
    draft: HeroDraft,
    event_type: str,
    metadata: dict | None = None,
    draft_team: DraftTeam | None = None,
) -> None:
    """
    Broadcast the current HeroDraft state to WebSocket consumers.

    Used for state changes like pause/resume where the event is already created.
    This avoids creating duplicate events.

    Args:
        draft: HeroDraft instance (should be refreshed from DB)
        event_type: Type of event for logging (e.g., "draft_paused", "draft_resumed")
        metadata: Additional event metadata (optional, e.g., countdown_seconds)
        draft_team: DraftTeam instance (optional, for captain_connected/disconnected events)
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "broadcast_skipped",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            reason="no_channel_layer",
            draft_id=draft.id,
        )
        return

    payload = {
        "type": "herodraft.event",
        "event_type": event_type,
    }

    if metadata:
        payload["metadata"] = metadata

    # Include draft_team with captain data for connection events
    if draft_team:
        payload["draft_team"] = DraftTeamSerializerFull(draft_team).data

    try:
        draft = herodraft_state_queryset().get(id=draft.id)
        payload["draft_state"] = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(
            "broadcast_serialize_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            draft_id=draft.id,
            error=str(e),
        )
        return  # Don't broadcast without state

    room_group_name = f"herodraft_{draft.id}"

    try:
        async_to_sync(channel_layer.group_send)(room_group_name, payload)
        log.debug(
            "broadcast_sent",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            event_type=event_type,
            draft_id=draft.id,
        )
    except Exception as e:
        log.warning(
            "broadcast_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            event_type=event_type,
            draft_id=draft.id,
            error=str(e),
        )
