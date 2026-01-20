"""
WebSocket consumers for draft event broadcasting.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

log = logging.getLogger(__name__)


class DraftConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for draft-specific events."""

    async def connect(self):
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

        # Send recent events on connect
        recent_events = await self.get_recent_events(self.draft_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": recent_events,
                }
            )
        )

    async def disconnect(self, close_code):
        # Leave draft group
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
    def draft_exists(self, draft_id):
        from app.models import Draft

        return Draft.objects.filter(pk=draft_id).exists()

    @database_sync_to_async
    def get_recent_events(self, draft_id, limit=20):
        from app.models import DraftEvent
        from app.serializers import DraftEventSerializer

        events = DraftEvent.objects.filter(draft_id=draft_id)[:limit]
        return DraftEventSerializer(events, many=True).data


class TournamentConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for tournament-wide events."""

    async def connect(self):
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


class HeroDraftConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    async def connect(self):
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.room_group_name = f"herodraft_{self.draft_id}"
        self.user = self.scope.get("user")
        self._connection_tracked = False

        # Verify draft exists
        draft_exists = await self.draft_exists(self.draft_id)
        if not draft_exists:
            log.warning(f"HeroDraft {self.draft_id} not found, closing connection")
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Track connection count for tick broadcaster
        await self.track_connection(True)

        # Send initial state
        try:
            initial_state = await self.get_draft_state(self.draft_id)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "initial_state",
                        "draft_state": initial_state,
                    }
                )
            )

            # Start tick broadcaster if draft is in drafting state
            if initial_state.get("state") == "drafting":
                await self.maybe_start_tick_broadcaster()

        except Exception as e:
            log.error(
                f"Failed to send initial state for herodraft {self.draft_id}: {e}"
            )
            await self.close()
            return

        # Mark captain as connected if authenticated
        if self.user and self.user.is_authenticated:
            await self.mark_captain_connected(self.draft_id, self.user, True)

    async def disconnect(self, close_code):
        # Track disconnection
        if hasattr(self, "_connection_tracked") and self._connection_tracked:
            await self.track_connection(False)

        # Mark captain as disconnected
        if (
            hasattr(self, "user")
            and hasattr(self, "draft_id")
            and self.user
            and self.user.is_authenticated
        ):
            try:
                await self.mark_captain_connected(self.draft_id, self.user, False)
            except Exception as e:
                log.error(
                    f"Failed to mark captain disconnected for herodraft {self.draft_id}: {e}"
                )

        # Leave room group
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    @database_sync_to_async
    def track_connection(self, is_connecting: bool):
        """Track WebSocket connection count in Redis."""
        from app.tasks.herodraft_tick import (
            decrement_connection_count,
            increment_connection_count,
        )

        try:
            if is_connecting:
                increment_connection_count(self.draft_id)
                self._connection_tracked = True
            else:
                decrement_connection_count(self.draft_id)
                self._connection_tracked = False
        except Exception as e:
            log.warning(f"Failed to track connection for draft {self.draft_id}: {e}")

    @database_sync_to_async
    def maybe_start_tick_broadcaster(self):
        """Start tick broadcaster if not already running."""
        from app.tasks.herodraft_tick import start_tick_broadcaster

        try:
            start_tick_broadcaster(self.draft_id)
        except Exception as e:
            log.warning(
                f"Failed to start tick broadcaster for draft {self.draft_id}: {e}"
            )

    async def receive(self, text_data):
        # Read-only consumer - ignore incoming messages
        pass

    async def herodraft_event(self, event):
        """Handle herodraft.event messages from channel layer."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_event",
                    "event_type": event.get("event_type"),
                    "event_id": event.get("event_id"),
                    "draft_team": event.get("draft_team"),
                    "draft_state": event.get("draft_state"),
                    "timestamp": event.get("timestamp"),
                }
            )
        )

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

    @database_sync_to_async
    def draft_exists(self, draft_id):
        from app.models import HeroDraft

        return HeroDraft.objects.filter(id=draft_id).exists()

    @database_sync_to_async
    def get_draft_state(self, draft_id):
        from app.models import HeroDraft
        from app.serializers import HeroDraftSerializer

        draft = HeroDraft.objects.get(id=draft_id)
        return HeroDraftSerializer(draft).data

    @database_sync_to_async
    def mark_captain_connected(self, draft_id, user, is_connected):
        from django.db import transaction

        from app.models import HeroDraft, HeroDraftEvent

        try:
            with transaction.atomic():
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)

                draft_team = draft.draft_teams.filter(
                    tournament_team__captain=user
                ).first()

                if draft_team:
                    draft_team.is_connected = is_connected
                    draft_team.save()

                    event_type = (
                        "captain_connected" if is_connected else "captain_disconnected"
                    )
                    HeroDraftEvent.objects.create(
                        draft=draft,
                        event_type=event_type,
                        draft_team=draft_team,
                        metadata={"user_id": user.id},
                    )

                    # Handle pause/resume on disconnect
                    if not is_connected and draft.state == "drafting":
                        draft.state = "paused"
                        draft.save()
                        HeroDraftEvent.objects.create(
                            draft=draft,
                            event_type="draft_paused",
                            draft_team=draft_team,
                            metadata={"reason": "captain_disconnected"},
                        )
                    elif is_connected and draft.state == "paused":
                        # Check if both captains connected
                        all_connected = all(
                            t.is_connected for t in draft.draft_teams.all()
                        )
                        if all_connected:
                            draft.state = "drafting"
                            draft.save()
                            HeroDraftEvent.objects.create(
                                draft=draft,
                                event_type="draft_resumed",
                                metadata={},
                            )
        except HeroDraft.DoesNotExist:
            return
