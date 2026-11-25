"""Tournament-wide WebSocket consumer."""

import json
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from app.consumer_db import consumer_db
from draft.services.team_state import recent_draft_events
from telemetry.websocket import TelemetryConsumerMixin
from tournament.models import Tournament


class TournamentConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    """WebSocket consumer for tournament-wide events."""

    async def connect(self) -> None:
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

    async def disconnect(self, close_code: int) -> None:
        await self.telemetry_disconnect(close_code)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data: str) -> None:
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event: dict[str, Any]) -> None:
        """Handle draft.event messages from channel layer."""
        message = {
            "type": "draft_event",
            "event": event["payload"],
        }
        # Include draft state if available (allows clients to update without API calls)
        if "draft_state" in event:
            message["draft_state"] = event["draft_state"]
        await self.send(text_data=json.dumps(message))

    async def lobby_event(self, event: dict[str, object]) -> None:
        """A game's dota_lobby lobby changed (lobby.broadcast). No password."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "lobby_event",
                    "game_id": event.get("game_id"),
                    "game_lobby_id": event.get("game_lobby_id"),
                    "state": event.get("state"),
                    "match_id": event.get("match_id"),
                    "provisional_winner_side": event.get("provisional_winner_side"),
                }
            )
        )

    async def bracket_update(self, event: dict[str, object]) -> None:
        """A game's bracket data changed; clients refetch the bracket."""
        await self.send(
            text_data=json.dumps(
                {"type": "bracket_update", "game_id": event.get("game_id")}
            )
        )

    async def tournament_update(self, event: dict[str, object]) -> None:
        """Teams, members, placements or settings changed; clients refetch."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "tournament_update",
                    "kind": event.get("kind"),
                    "team_id": event.get("team_id"),
                }
            )
        )

    @consumer_db
    def tournament_exists(self, tournament_id: int) -> bool:
        return Tournament.objects.filter(pk=tournament_id).exists()

    @consumer_db
    def get_recent_events(self, tournament_id: int, limit: int = 20) -> list[dict]:
        return recent_draft_events(tournament_id, limit)
