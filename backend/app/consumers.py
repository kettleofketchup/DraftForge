"""
WebSocket consumers for draft event broadcasting.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

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
        await self.telemetry_disconnect(close_code)
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
