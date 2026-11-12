"""
WebSocket consumers for draft event broadcasting.
"""

import json
import time
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import transaction
from django.utils import timezone

from app.broadcast import broadcast_herodraft_state
from app.cache_utils import invalidate_obj
from app.consumers_base import BaseDraftConsumer, consumer_db
from app.draft_state import build_draft_state
from app.functions.teamdraft import emit_event, team_payload
from app.models import (
    Draft,
    DraftEvent,
    DraftTeam,
    HeroDraft,
    HeroDraftEvent,
    HeroDraftState,
    Team,
    Tournament,
)
from app.serializers import DraftEventSerializer, HeroDraftSerializer
from app.tasks.draft_tick import CAPTAIN_CHANNEL_TTL, TickDriver
from app.tasks.teamdraft_tick import (
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
        # Get events from the tournament's draft
        try:
            draft = Draft.objects.get(tournament_id=tournament_id)
            events = DraftEvent.objects.filter(draft=draft)[:limit]
            return DraftEventSerializer(events, many=True).data
        except Draft.DoesNotExist:
            return []


class HeroDraftConsumer(BaseDraftConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    PING_ENABLED = True
    kick_duplicate_captain_connections = True
    clear_heartbeat_on_disconnect = True

    # --- Abstract method implementations ---

    def get_room_group_prefix(self) -> str:
        return "herodraft"

    @consumer_db
    def draft_exists(self, draft_id: int) -> bool:
        return HeroDraft.objects.filter(id=draft_id).exists()

    @consumer_db
    def get_initial_state_data(self, draft_id: int) -> dict:
        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft_id)
        return HeroDraftSerializer(draft).data

    @consumer_db
    def get_captain_draft_team(
        self, draft_id: int, user: "AbstractBaseUser"
    ) -> DraftTeam | None:
        try:
            draft = HeroDraft.objects.get(id=draft_id)
            return draft.draft_teams.filter(tournament_team__captain=user).first()
        except HeroDraft.DoesNotExist:
            return None

    def get_active_draft_state_values(self) -> list[str]:
        return [HeroDraftState.DRAFTING.value]

    def _follow_tick_state(self, state: str | None) -> None:
        # The tick loop runs through RESUMING; any other state ends it.
        self._tick_wanted = state in (
            HeroDraftState.DRAFTING.value,
            HeroDraftState.RESUMING.value,
        )

    # --- Connect / Disconnect ---

    async def connect(self) -> None:
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

    async def disconnect(self, close_code: int) -> None:
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

    async def receive(self, text_data: str) -> None:
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

    async def on_captain_state_change(
        self, draft_id: int, user: "AbstractBaseUser", is_connected: bool
    ) -> None:
        await self.in_draft_order(
            lambda: self._apply_captain_state_change(draft_id, user, is_connected)
        )

    @consumer_db
    def _apply_captain_state_change(
        self, draft_id: int, user: "AbstractBaseUser", is_connected: bool
    ) -> None:
        """Mark captain connected/disconnected and handle pause-on-disconnect.

        Only pauses during DRAFTING state (not RESUMING) to prevent infinite
        time exploit. Broadcasts state changes after transaction commits.
        """

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

    # --- HeroDraft-specific channel layer handlers ---

    async def herodraft_kicked(self, event: dict[str, Any]) -> None:
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

    async def herodraft_event(self, event: dict[str, Any]) -> None:
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
            self._follow_tick_state(event["draft_state"].get("state"))
        if "timestamp" in event and event["timestamp"] is not None:
            message["timestamp"] = event["timestamp"]
        if "metadata" in event and event["metadata"] is not None:
            message["metadata"] = event["metadata"]

        await self.send(text_data=json.dumps(message))

    async def herodraft_tick(self, event: dict[str, Any]) -> None:
        """Forward tick anchors from the channel layer to this WS client.

        Anchor fields (server_time + round_started_at + round_grace_time_ms
        + raw team reserves + resuming_until) drive the client-side rAF
        countdown. See `backend/app/tasks/herodraft_tick.py::broadcast_tick`
        for the producer side.
        """
        self._follow_tick_state(event.get("draft_state"))
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
