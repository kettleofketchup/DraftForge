"""
WebSocket consumers for draft event broadcasting.
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from app.consumers_base import BaseDraftConsumer
from telemetry.logging import get_logger
from telemetry.websocket import TelemetryConsumerMixin

log = get_logger(__name__)


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

    # --- Connect / Disconnect ---

    async def connect(self):
        # Set early for kick detection (base_connect re-sets these to same values)
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.user = self.scope.get("user")

        # Kick any existing captain connection BEFORE base_connect()
        if self.user and self.user.is_authenticated:
            existing_channel = await self._get_existing_captain_channel()
            if existing_channel and existing_channel != self.channel_name:
                await self._kick_channel(existing_channel)

        result = await self.base_connect()
        if result:
            log.info(
                "herodraft_connected",
                system="herodraft",
                subsystem="connection",
                draft_id=self.draft_id,
                user_id=(
                    self.user.id if self.user and self.user.is_authenticated else None
                ),
                is_captain=self._is_captain,
            )

    async def disconnect(self, close_code):
        log.info(
            "herodraft_disconnected",
            system="herodraft",
            subsystem="connection",
            draft_id=getattr(self, "draft_id", None),
            user_id=(
                self.user.id
                if getattr(self, "user", None) and self.user.is_authenticated
                else None
            ),
            is_captain=getattr(self, "_is_captain", False),
            close_code=close_code,
            was_kicked=getattr(self, "_was_kicked", False),
        )
        await self.base_disconnect(close_code)

    # --- Receive ---

    async def receive(self, text_data):
        """Handle incoming WebSocket messages from clients.

        Wrapped in a `ws.message` span via `traced_message` so each
        incoming WS message appears as its own trace in Tempo with
        `ws.message_type` set. Handler spans (e.g. `ws.heartbeat`)
        become children of this span — Tempo shows the full waterfall
        of "message dispatch overhead → handler work" without needing
        to instrument every handler separately.
        """
        if not self._is_captain:
            return  # Only process messages from captains

        try:
            data = json.loads(text_data)
            msg_type = data.get("type", "unknown")

            async with self.traced_message(msg_type):
                if msg_type == "heartbeat":
                    await self.handle_heartbeat()
        except json.JSONDecodeError:
            # Span deliberately NOT opened — there's no message type to
            # tag the span with, and a `ws.message[type=unknown]` span on
            # every byte of garbage would just pollute Tempo. Log only.
            log.warning(
                "ws_malformed_message",
                system="herodraft",
                subsystem="connection",
                draft_id=self.draft_id,
                user_id=self.user.id,
            )

    # --- Captain state change (pause-on-disconnect) ---

    @database_sync_to_async
    def on_captain_state_change(self, draft_id, user, is_connected):
        """Mark captain connected/disconnected and handle pause-on-disconnect.

        Only pauses during DRAFTING state (not RESUMING) to prevent infinite
        time exploit. Broadcasts state changes after transaction commits.
        """
        from django.db import transaction

        from app.broadcast import broadcast_herodraft_state
        from app.models import HeroDraft, HeroDraftEvent, HeroDraftState

        broadcast_event_type = None
        should_broadcast = False

        try:
            with transaction.atomic():
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)

                draft_team = draft.draft_teams.filter(
                    tournament_team__captain=user
                ).first()

                if draft_team:
                    # Determine before-mutation whether this is a reconnect
                    # (i.e., the captain has connected at least once before in
                    # this draft session). The frontend uses this to render
                    # "joined" vs "reconnected" toast text without doing its
                    # own session-tracking — server is the source of truth on
                    # connection history.
                    is_reconnect = (
                        is_connected
                        and HeroDraftEvent.objects.filter(
                            draft=draft,
                            draft_team=draft_team,
                            event_type="captain_connected",
                        ).exists()
                    )

                    draft_team.is_connected = is_connected
                    draft_team.save()

                    event_type = (
                        "captain_connected" if is_connected else "captain_disconnected"
                    )
                    HeroDraftEvent.objects.create(
                        draft=draft,
                        event_type=event_type,
                        draft_team=draft_team,
                        metadata={
                            "user_id": user.id,
                            "username": user.username,
                            "is_reconnect": is_reconnect,
                        },
                    )
                    log.info(
                        "captain_state_changed",
                        system="herodraft",
                        subsystem="connection",
                        draft_id=draft_id,
                        user_id=user.id,
                        username=user.username,
                        is_connected=is_connected,
                        draft_state=draft.state,
                    )

                    # Handle pause on disconnect - only during DRAFTING phase
                    # (when timers are running and picks matter)
                    # Ignore disconnects during RESUMING to prevent infinite time exploit
                    if not is_connected and draft.state == HeroDraftState.DRAFTING:
                        draft.state = HeroDraftState.PAUSED
                        draft.paused_at = timezone.now()
                        draft.save()
                        HeroDraftEvent.objects.create(
                            draft=draft,
                            event_type="draft_paused",
                            draft_team=draft_team,
                            metadata={"reason": "captain_disconnected"},
                        )
                        log.info(
                            "captain_disconnect_paused",
                            system="herodraft",
                            subsystem="connection",
                            draft_id=draft_id,
                            user_id=user.id,
                            username=user.username,
                            previous_state=HeroDraftState.DRAFTING.value,
                        )
                        broadcast_event_type = "draft_paused"
                        should_broadcast = True
                    elif is_connected and draft.state == HeroDraftState.PAUSED:
                        broadcast_event_type = event_type
                        should_broadcast = True
                    else:
                        broadcast_event_type = event_type
                        should_broadcast = True

        except HeroDraft.DoesNotExist:
            return

        if should_broadcast and broadcast_event_type:
            try:
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=draft_id)
                fresh_draft_team = None
                for dt in draft.draft_teams.all():
                    if dt.captain and dt.captain.id == user.id:
                        fresh_draft_team = dt
                        break

                broadcast_herodraft_state(
                    draft, broadcast_event_type, draft_team=fresh_draft_team
                )
            except Exception as e:
                log.error(
                    "captain_state_broadcast_failed",
                    system="herodraft",
                    subsystem="connection",
                    draft_id=draft_id,
                    user_id=user.id,
                    error=str(e),
                )

    # --- HeroDraft-specific kick detection ---

    async def _get_existing_captain_channel(self):
        """Get the existing captain channel from Redis, if any."""
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self._captain_channel_key(self.draft_id, self.user.id)
        return r.get(channel_key)

    async def _kick_channel(self, old_channel):
        """Send kick message to an existing captain connection."""
        log.info(
            "captain_kicked",
            system="herodraft",
            subsystem="connection",
            draft_id=self.draft_id,
            user_id=self.user.id,
            old_channel=old_channel,
            new_channel=self.channel_name,
        )
        try:
            await self.channel_layer.send(
                old_channel,
                {"type": "herodraft.kicked", "reason": "new_connection"},
            )
        except Exception as e:
            log.warning(
                "captain_kick_failed",
                system="herodraft",
                subsystem="connection",
                draft_id=self.draft_id,
                user_id=self.user.id,
                old_channel=old_channel,
                error=str(e),
            )

    # --- HeroDraft-specific channel layer handlers ---

    async def herodraft_kicked(self, event):
        """Handle being kicked by a newer connection."""
        reason = event.get("reason", "unknown")
        log.info(
            "captain_was_kicked",
            system="herodraft",
            subsystem="connection",
            draft_id=self.draft_id,
            user_id=self.user.id,
            reason=reason,
        )
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
        """Forward tick anchors from the channel layer to this WS client.

        Anchor fields (server_time + round_started_at + round_grace_time_ms
        + raw team reserves + resuming_until) drive the client-side rAF
        countdown. See `backend/app/tasks/herodraft_tick.py::broadcast_tick`
        for the producer side.
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_tick",
                    "draft_state": event.get("draft_state"),
                    "server_time": event.get("server_time"),
                    # DRAFTING anchors
                    "current_round": event.get("current_round"),
                    "active_team_id": event.get("active_team_id"),
                    "round_started_at": event.get("round_started_at"),
                    "round_grace_time_ms": event.get("round_grace_time_ms"),
                    "team_a_id": event.get("team_a_id"),
                    "team_a_reserve_ms": event.get("team_a_reserve_ms"),
                    "team_b_id": event.get("team_b_id"),
                    "team_b_reserve_ms": event.get("team_b_reserve_ms"),
                    # RESUMING anchor
                    "resuming_until": event.get("resuming_until"),
                }
            )
        )
