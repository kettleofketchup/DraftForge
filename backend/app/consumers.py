"""
WebSocket consumers for draft event broadcasting.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from app.consumers_base import BaseDraftConsumer
from telemetry.websocket import TelemetryConsumerMixin

log = logging.getLogger(__name__)


class DraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    """WebSocket consumer for draft-specific events."""

    async def connect(self):
        await self.telemetry_connect()
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.room_group_name = f"draft_{self.draft_id}"

        # Validate draft exists
        draft_exists = await self.draft_exists(self.draft_id)
        if not draft_exists:
            await self.close()
            return

        # Join draft group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send recent events and current draft state on connect
        recent_events = await self.get_recent_events(self.draft_id)
        draft_state = await self.get_draft_state(self.draft_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": recent_events,
                    "draft_state": draft_state,
                }
            )
        )

    async def disconnect(self, close_code):
        await self.telemetry_disconnect(close_code)
        # Leave draft group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event):
        """Handle draft.event messages from channel layer."""
        log.debug(
            f"DraftConsumer sending draft_event to client "
            f"(draft={self.draft_id}, channel={self.channel_name})"
        )
        message = {
            "type": "draft_event",
            "event": event["payload"],
        }
        # Include draft state if available (allows clients to update without API calls)
        if "draft_state" in event:
            message["draft_state"] = event["draft_state"]
        await self.send(text_data=json.dumps(message))

    async def force_disconnect(self, event):
        """Test-only: server-initiated connection close."""
        await self.close(code=1012)  # Service Restart

    @database_sync_to_async
    def draft_exists(self, draft_id):
        from app.models import Draft

        return Draft.objects.filter(pk=draft_id).exists()

    @database_sync_to_async
    def get_recent_events(self, draft_id, limit=20):
        from app.models import DraftEvent
        from app.serializers import DraftEventSerializer

        events = DraftEvent.objects.filter(draft_id=draft_id)[:limit]
        return DraftEventSerializer(events, many=True).data

    @database_sync_to_async
    def get_draft_state(self, draft_id):
        from app.models import Draft
        from app.serializers import DraftSerializerSlim, _build_users_dict

        try:
            # Note: users_remaining is a property, not a relation, so it can't be prefetched
            draft = Draft.objects.prefetch_related(
                "draft_rounds__captain",
                "draft_rounds__choice",
                "tournament__teams__captain",
                "tournament__teams__members",
                "tournament__users",  # Prefetch users for users_remaining calculation
            ).get(pk=draft_id)
            data = DraftSerializerSlim(draft).data

            # Add _users dict for frontend cache hydration
            # Convert int keys to strings for consistency with broadcast path
            # (msgpack strict mode forbids int map keys in channel layer)
            data["_users"] = {
                str(k): v for k, v in _build_users_dict(draft.tournament).items()
            }
            return data
        except Draft.DoesNotExist:
            return None


class TournamentConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    """WebSocket consumer for tournament-wide events."""

    async def connect(self):
        await self.telemetry_connect()
        self.tournament_id = self.scope["url_route"]["kwargs"]["tournament_id"]
        self.room_group_name = f"tournament_{self.tournament_id}"

        # Validate tournament exists
        tournament_exists = await self.tournament_exists(self.tournament_id)
        if not tournament_exists:
            await self.close()
            return

        # Join tournament group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send recent events on connect
        recent_events = await self.get_recent_events(self.tournament_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": recent_events,
                }
            )
        )

    async def disconnect(self, close_code):
        await self.telemetry_disconnect(close_code)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event):
        """Handle draft.event messages from channel layer."""
        message = {
            "type": "draft_event",
            "event": event["payload"],
        }
        # Include draft state if available (allows clients to update without API calls)
        if "draft_state" in event:
            message["draft_state"] = event["draft_state"]
        await self.send(text_data=json.dumps(message))

    @database_sync_to_async
    def tournament_exists(self, tournament_id):
        from app.models import Tournament

        return Tournament.objects.filter(pk=tournament_id).exists()

    @database_sync_to_async
    def get_recent_events(self, tournament_id, limit=20):
        from app.models import Draft, DraftEvent
        from app.serializers import DraftEventSerializer

        # Get events from the tournament's draft
        try:
            draft = Draft.objects.get(tournament_id=tournament_id)
            events = DraftEvent.objects.filter(draft=draft)[:limit]
            return DraftEventSerializer(events, many=True).data
        except Draft.DoesNotExist:
            return []


class HeroDraftConsumer(BaseDraftConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    # --- Abstract method implementations ---

    def get_room_group_prefix(self) -> str:
        return "herodraft"

    @database_sync_to_async
    def draft_exists(self, draft_id):
        from app.models import HeroDraft

        return HeroDraft.objects.filter(id=draft_id).exists()

    @database_sync_to_async
    def get_initial_state_data(self, draft_id):
        from app.models import HeroDraft
        from app.serializers import HeroDraftSerializer

        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft_id)
        return HeroDraftSerializer(draft).data

    @database_sync_to_async
    def get_captain_draft_team(self, draft_id, user):
        from app.models import HeroDraft

        try:
            draft = HeroDraft.objects.get(id=draft_id)
            return draft.draft_teams.filter(tournament_team__captain=user).first()
        except HeroDraft.DoesNotExist:
            return None

    def get_active_draft_state_values(self) -> list[str]:
        from app.models import HeroDraftState

        return [HeroDraftState.DRAFTING.value]

    def get_paused_state_value(self) -> str:
        from app.models import HeroDraftState

        return HeroDraftState.PAUSED.value

    # --- Connect / Disconnect ---

    async def connect(self):
        # Pre-connection: need draft_id and user for kick detection
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.user = self.scope.get("user")

        # Kick any existing captain connection BEFORE base_connect()
        # (base_connect will re-set draft_id/user, but we need them here first)
        if self.user and self.user.is_authenticated:
            draft_team = await self.get_captain_draft_team(self.draft_id, self.user)
            if draft_team is not None:
                await self.kick_existing_captain_connection()

        await self.base_connect()

    async def disconnect(self, close_code):
        await self.base_disconnect(close_code)

    # --- Receive ---

    async def receive(self, text_data):
        """Handle incoming WebSocket messages from clients."""
        if not self._is_captain:
            return  # Only process messages from captains

        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                await self.handle_heartbeat()
        except json.JSONDecodeError:
            pass  # Ignore malformed messages

    # --- HeroDraft-specific channel layer handlers ---

    async def kick_existing_captain_connection(self):
        """Kick any existing WebSocket connection for this captain."""
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self._captain_channel_key(self.draft_id, self.user.id)

        old_channel = r.get(channel_key)
        log.info(
            f"[KICK DEBUG] Checking kick for user {self.user.id} in draft {self.draft_id}: "
            f"old_channel={old_channel!r}, new_channel={self.channel_name!r}"
        )
        if old_channel and old_channel != self.channel_name:
            log.info(
                f"Kicking existing captain connection for user {self.user.id} "
                f"in draft {self.draft_id}: {old_channel} -> {self.channel_name}"
            )
            # Send kick message to old connection
            try:
                await self.channel_layer.send(
                    old_channel,
                    {"type": "herodraft.kicked", "reason": "new_connection"},
                )
                log.info(f"[KICK DEBUG] Sent kick message to {old_channel}")
            except Exception as e:
                log.warning(f"Failed to send kick message to {old_channel}: {e}")
        else:
            log.info(f"[KICK DEBUG] No kick needed - old_channel={old_channel!r}")

    async def herodraft_kicked(self, event):
        """Handle being kicked by a newer connection."""
        reason = event.get("reason", "unknown")
        log.info(f"Captain {self.user.id} kicked from draft {self.draft_id}: {reason}")
        # Mark this connection as kicked so disconnect() knows not to trigger
        # disconnect events (the new connection is already active)
        self._was_kicked = True
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_kicked",
                    "reason": reason,
                }
            )
        )
        await self.close(code=4000)  # Custom close code for "kicked"

    async def herodraft_event(self, event):
        """Handle herodraft.event messages from channel layer."""
        # Build message with only fields that have actual values
        # Using .get() with missing keys returns None, which serializes to null
        # and fails Zod validation where .optional() expects undefined, not null
        message = {
            "type": "herodraft_event",
            "event_type": event.get("event_type"),
        }
        # Only include optional fields if they have values
        if "event_id" in event and event["event_id"] is not None:
            message["event_id"] = event["event_id"]
        if "draft_team" in event and event["draft_team"] is not None:
            message["draft_team"] = event["draft_team"]
        if "draft_state" in event and event["draft_state"] is not None:
            message["draft_state"] = event["draft_state"]
        if "timestamp" in event and event["timestamp"] is not None:
            message["timestamp"] = event["timestamp"]
        if "metadata" in event and event["metadata"] is not None:
            message["metadata"] = event["metadata"]

        await self.send(text_data=json.dumps(message))

    async def herodraft_tick(self, event):
        """Handle tick updates during active drafting."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_tick",
                    "current_round": event.get("current_round"),
                    "active_team_id": event.get("active_team_id"),
                    "grace_time_remaining_ms": event.get("grace_time_remaining_ms"),
                    "team_a_id": event.get("team_a_id"),
                    "team_a_reserve_ms": event.get("team_a_reserve_ms"),
                    "team_b_id": event.get("team_b_id"),
                    "team_b_reserve_ms": event.get("team_b_reserve_ms"),
                    "draft_state": event.get("draft_state"),
                }
            )
        )
