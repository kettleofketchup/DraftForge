"""
WebSocket consumers for draft event broadcasting.
"""

import json
import time
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from app.cache_utils import invalidate_obj
from app.consumer_db import consumer_db
from app.models import (
    Draft,
    DraftEvent,
    Team,
    Tournament,
)
from app.serializers import DraftEventSerializer
from draft.consumers.base import BaseDraftConsumer
from draft.services.team import emit_event, team_payload
from draft.services.team_state import build_draft_state, recent_draft_events
from draft.tasks.draft_tick import CAPTAIN_CHANNEL_TTL, TickDriver
from draft.tasks.team_tick import (
    TEAM_TICK_DRIVER,
    captain_conn_key,
    captain_is_fresh,
)
from telemetry.logging import get_logger
from telemetry.websocket import TelemetryConsumerMixin

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

log = get_logger(__name__)


class DraftConsumer(BaseDraftConsumer):
    """WebSocket consumer for draft-specific events."""

    PING_ENABLED = True
    kick_duplicate_captain_connections = False
    clear_heartbeat_on_disconnect = False

    def get_room_group_prefix(self) -> str:
        return "draft"

    def get_redis_prefix(self) -> str:
        return "teamdraft"

    @consumer_db
    def draft_exists(self, draft_id: int) -> bool:
        return Draft.objects.filter(pk=draft_id).exists()

    @consumer_db
    def get_initial_state_data(self, draft_id: int) -> dict | None:
        return build_draft_state(draft_id, fresh=False)

    @consumer_db
    def get_captain_draft_team(
        self, draft_id: int, user: "AbstractBaseUser"
    ) -> "Team | None":
        return Team.objects.filter(tournament__draft__pk=draft_id, captain=user).first()

    def get_active_draft_state_values(self) -> list[str]:
        return ["drafting", "resuming"]

    def get_tick_driver(self) -> TickDriver | None:
        return TEAM_TICK_DRIVER

    def should_start_tick_broadcaster(self, initial_state: dict | None) -> bool:
        return bool(
            initial_state
            and (
                initial_state.get("clock_armed")
                or initial_state.get("state") == "paused"
            )
        )

    @consumer_db
    def _set_presence(
        self, draft_id: int, user: "AbstractBaseUser", is_connected: bool
    ) -> None:
        team = Team.objects.filter(tournament__draft__pk=draft_id, captain=user).first()
        if team is None:
            return
        draft = Draft.objects.get(pk=draft_id)
        active = draft.active_round
        payload = {
            "pick_number": active.pick_number if active else None,
            **team_payload(team),
            "is_active_captain": bool(active and active.captain_id == user.pk),
        }
        if is_connected:
            team.draft_is_connected = True
            team.draft_has_connected = True
            team.save(update_fields=["draft_is_connected", "draft_has_connected"])
            invalidate_obj(team.tournament)
            emit_event(draft, "captain_connected", payload)
            log.info(
                "teamdraft_captain_connected",
                system="teamdraft",
                subsystem="connection",
                draft_id=draft_id,
                user_id=user.pk,
            )
        else:
            team.draft_is_connected = False
            team.save(update_fields=["draft_is_connected"])
            invalidate_obj(team.tournament)
            emit_event(draft, "captain_disconnected", payload)
            log.info(
                "teamdraft_captain_disconnected",
                system="teamdraft",
                subsystem="connection",
                draft_id=draft_id,
                user_id=user.pk,
            )

    async def on_captain_state_change(
        self, draft_id: int, user: "AbstractBaseUser", is_connected: bool
    ) -> None:
        r = self._redis()
        key = captain_conn_key(draft_id, user.id)
        if is_connected:
            r.incr(key)
            r.expire(key, CAPTAIN_CHANNEL_TTL)
        else:
            count = r.decr(key)
            if count <= 0:
                r.delete(key)
            if count < 0:
                log.warning(
                    "captain_conn_count_negative",
                    system="teamdraft",
                    subsystem="connection",
                    draft_id=draft_id,
                    user_id=user.id,
                )
            if count > 0:
                return
        await self.in_draft_order(
            lambda: self._set_presence(draft_id, user, is_connected)
        )

    @consumer_db
    def _restore_presence(self, draft_id: int, user: "AbstractBaseUser") -> None:
        team = Team.objects.filter(tournament__draft__pk=draft_id, captain=user).first()
        if team is None or team.draft_has_connected:
            return
        team.draft_is_connected = True
        team.draft_has_connected = True
        team.save(update_fields=["draft_is_connected", "draft_has_connected"])
        invalidate_obj(team.tournament)
        log.info(
            "teamdraft_captain_presence_restored",
            system="teamdraft",
            subsystem="connection",
            draft_id=draft_id,
            user_id=user.pk,
        )

    async def handle_heartbeat(self) -> None:
        if not self._is_captain:
            await super().handle_heartbeat()
            return
        was_fresh = await sync_to_async(
            self._captain_is_fresh, thread_sensitive=False
        )()
        await super().handle_heartbeat()
        if not was_fresh:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "captain.heartbeat",
                    "captain_id": self.user.id,
                    "fresh": True,
                },
            )
        if not await sync_to_async(self._extend_captain_conn, thread_sensitive=False)():
            return
        await self.in_draft_order(
            lambda: self._restore_presence(self.draft_id, self.user)
        )

    def _captain_is_fresh(self) -> bool:
        return captain_is_fresh(self._redis(), self.draft_id, self.user.id, time.time())

    def _extend_captain_conn(self) -> bool:
        r = self._redis()
        key = captain_conn_key(self.draft_id, self.user.id)
        if not r.exists(key):
            return False
        r.expire(key, CAPTAIN_CHANNEL_TTL)
        return True

    async def draft_tick(self, event: dict[str, Any]) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "type": "draft_tick",
                    **{k: v for k, v in event.items() if k != "type"},
                }
            )
        )

    async def captain_heartbeat(self, event: dict[str, Any]) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "type": "captain_heartbeat",
                    "captain_id": event["captain_id"],
                    "fresh": event["fresh"],
                }
            )
        )

    def _captain_fresh_map(self, initial_state: dict | None) -> dict[str, bool]:
        r = self._redis()
        now_ts = time.time()
        teams = ((initial_state or {}).get("tournament") or {}).get("teams") or []
        return {
            str(team["captain"]): captain_is_fresh(
                r, self.draft_id, team["captain"], now_ts
            )
            for team in teams
            if team.get("captain") is not None
        }

    async def send_initial_messages(self, initial_state: dict | None) -> None:
        captain_fresh = await sync_to_async(
            self._captain_fresh_map, thread_sensitive=False
        )(initial_state)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_state",
                    "draft_state": initial_state,
                    "captain_fresh": captain_fresh,
                    "server_time": timezone.now().isoformat(),
                }
            )
        )
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": await self.get_recent_events(self.draft_id),
                }
            )
        )

    async def connect(self) -> None:
        result = await self.base_connect()
        if result:
            log.info(
                "teamdraft_connected",
                system="teamdraft",
                subsystem="connection",
                draft_id=self.draft_id,
                user_id=(
                    self.user.id if self.user and self.user.is_authenticated else None
                ),
                is_captain=self._is_captain,
            )

    async def disconnect(self, close_code: int | None) -> None:
        log.info(
            "teamdraft_disconnected",
            system="teamdraft",
            subsystem="connection",
            draft_id=getattr(self, "draft_id", None),
            user_id=(
                self.user.id
                if getattr(self, "user", None) and self.user.is_authenticated
                else None
            ),
            is_captain=getattr(self, "_is_captain", False),
            close_code=close_code,
        )
        await self.base_disconnect(close_code)

    async def receive(self, text_data: str | None) -> None:
        if not self._is_captain:
            return

        try:
            data = json.loads(text_data)
            msg_type = data.get("type", "unknown")

            async with self.traced_message(msg_type):
                if msg_type == "heartbeat":
                    await self.handle_heartbeat()
        except json.JSONDecodeError:
            log.warning(
                "ws_malformed_message",
                system="teamdraft",
                subsystem="connection",
                draft_id=getattr(self, "draft_id", None),
            )

    async def draft_event(self, event: dict[str, Any]) -> None:
        """Handle draft.event messages from channel layer."""
        log.debug(
            "draft_event_send",
            system="teamdraft",
            subsystem="connection",
            draft_id=self.draft_id,
            channel_name=self.channel_name,
        )
        message = {
            "type": "draft_event",
            "event": event["payload"],
        }
        # Include draft state if available (allows clients to update without API calls)
        if "draft_state" in event:
            message["draft_state"] = event["draft_state"]
            self._tick_wanted = self.should_start_tick_broadcaster(event["draft_state"])
        await self.send(text_data=json.dumps(message))

    async def force_disconnect(self, event: dict[str, Any]) -> None:
        """Test-only: server-initiated connection close."""
        # Daphne only lets a server send 1000 or 3000-4999; 1012 crashed the consumer.
        await self.close(code=4012)

    @consumer_db
    def get_recent_events(self, draft_id: int, limit: int = 20) -> list[dict]:
        events = DraftEvent.objects.filter(draft_id=draft_id)[:limit]
        return DraftEventSerializer(events, many=True).data


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

    @consumer_db
    def tournament_exists(self, tournament_id: int) -> bool:
        return Tournament.objects.filter(pk=tournament_id).exists()

    @consumer_db
    def get_recent_events(self, tournament_id: int, limit: int = 20) -> list[dict]:
        return recent_draft_events(tournament_id, limit)
