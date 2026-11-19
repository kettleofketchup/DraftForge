import json
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from app.consumers_base import BaseDraftConsumer, consumer_db
from app.tasks.draft_tick import TickDriver
from draft.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftState
from draft.serializers.hero import HeroDraftSerializer
from draft.services.hero_broadcast import broadcast_herodraft_state
from draft.services.hero_state import herodraft_state_queryset
from draft.tasks.hero_tick import HERO_TICK_DRIVER
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

log = get_logger(__name__)


class HeroDraftConsumer(BaseDraftConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    PING_ENABLED = True
    kick_duplicate_captain_connections = True
    clear_heartbeat_on_disconnect = True

    # --- Abstract method implementations ---

    def get_room_group_prefix(self) -> str:
        return "herodraft"

    def get_tick_driver(self) -> TickDriver | None:
        return HERO_TICK_DRIVER

    @consumer_db
    def draft_exists(self, draft_id: int) -> bool:
        return HeroDraft.objects.filter(id=draft_id).exists()

    @consumer_db
    def get_initial_state_data(self, draft_id: int) -> dict:
        draft = herodraft_state_queryset().get(id=draft_id)
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
        countdown. See `backend/draft/tasks/hero_tick.py::broadcast_tick`
        for the producer side.
        """
        self._follow_tick_state(event.get("draft_state"))
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_tick",
                    "draft_state": event.get("draft_state"),
                    "timer_enabled": event.get("timer_enabled", True),
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
