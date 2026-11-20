import json
import re
from datetime import datetime
from importlib import import_module
from time import monotonic
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from app.consumers_base import BaseDraftConsumer, consumer_db
from app.tasks.draft_tick import TickDriver
from draft.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftState
from draft.serializers.hero import HeroDraftSerializer
from draft.services.hero_broadcast import broadcast_herodraft_state
from draft.services.hero_chat import (
    CHAT_DELIVERY_CACHE_S,
    CHAT_RESYNC_EVENTS,
    REJECT_LOG_MAX,
    REJECT_LOG_WINDOW_S,
    SPECTATOR,
    ChatError,
    ChatErrorCode,
    ChatViewer,
    PostResult,
    authorize_post,
    check_rate_limit,
    draft_roster_user_ids,
    post_suggestion,
    post_text,
    resolve_chat_viewer,
    team_group_name,
    visible_messages,
)
from draft.services.hero_state import herodraft_state_queryset
from draft.tasks.hero_tick import HERO_TICK_DRIVER
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

log = get_logger(__name__)

_CLIENT_MSG_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CHAT_MESSAGE_TYPES = frozenset({"chat_send", "chat_suggest"})


def _session_alive(scope: dict[str, Any], user: Any) -> bool:
    if "activity" in scope:
        return True
    session = scope.get("session")
    if session is None or user is None or not user.is_authenticated:
        return True
    key = session.session_key
    if not key:
        return False
    store = import_module(settings.SESSION_ENGINE).SessionStore()
    return bool(store.exists(key))


def _created_before(message: dict[str, Any], joined_at: datetime | None) -> bool:
    if joined_at is None:
        return True
    try:
        created = datetime.fromisoformat(message["created_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return created < joined_at


class HeroDraftConsumer(BaseDraftConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    PING_ENABLED = True
    kick_duplicate_captain_connections = True
    clear_heartbeat_on_disconnect = True
    _chat_viewer: ChatViewer = SPECTATOR
    # Set when a viewer lookup failed; the socket is held as spectator until one succeeds.
    _chat_degraded: bool = False
    # Last successful team-delivery check; roster resyncs and viewer changes clear it.
    _chat_verified_at: float | None = None
    _reject_window_start: float = 0.0
    _reject_count: int = 0

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

    async def send_initial_messages(self, initial_state: dict | None) -> None:
        await super().send_initial_messages(initial_state)
        await self._chat_resync()

    # --- Chat ---

    def _chat_user_id(self) -> int | None:
        user = getattr(self, "user", None)
        if user is not None and user.is_authenticated:
            return user.pk
        return None

    def _fresh_chat_viewer(self) -> ChatViewer:
        if not _session_alive(self.scope, self.user):
            return ChatViewer(
                user_id=self._chat_user_id(),
                team_id=None,
                role="spectator",
                joined_at=None,
            )
        return resolve_chat_viewer(self.draft_id, self.user)

    @consumer_db
    def _resolve_chat_viewer(self) -> ChatViewer:
        return self._fresh_chat_viewer()

    @consumer_db
    def _chat_session_alive(self) -> bool:
        return _session_alive(self.scope, self.user)

    @consumer_db
    def _draft_roster_user_ids(self) -> set[int]:
        return draft_roster_user_ids(self.draft_id)

    @consumer_db
    def _post_chat(
        self, msg_type: str, data: dict[str, Any]
    ) -> tuple[ChatViewer, PostResult | ChatError]:
        viewer = self._fresh_chat_viewer()
        try:
            if msg_type == "chat_send":
                result = post_text(self.draft_id, self.user, data.get("body"), viewer)
            else:
                result = post_suggestion(
                    self.draft_id,
                    self.user,
                    data.get("kind"),
                    data.get("hero_id"),
                    viewer,
                )
        except ChatError as e:
            return viewer, e
        return viewer, result

    @consumer_db
    def _chat_history_messages(self, viewer: ChatViewer) -> list[dict[str, Any]]:
        return visible_messages(self.draft_id, viewer)

    async def _chat_bootstrap(self) -> None:
        await self._apply_chat_viewer(await self._resolve_chat_viewer())
        await self._send_chat_history()

    async def _chat_resync(self) -> None:
        try:
            await self._chat_bootstrap()
        except Exception as e:
            await self._chat_bootstrap_failed(e)

    async def _regroup(self, viewer: ChatViewer) -> None:
        try:
            await self._apply_chat_viewer(viewer)
            await self._send_chat_history()
        except Exception as e:
            await self._chat_bootstrap_failed(e)

    @staticmethod
    def _viewer_changed(old: ChatViewer, new: ChatViewer) -> bool:
        return (old.role, old.team_id) != (new.role, new.team_id)

    async def _send_chat_error(
        self, code: ChatErrorCode, client_msg_id: str | None
    ) -> None:
        frame: dict[str, Any] = {"type": "chat_error", "code": code}
        if client_msg_id is not None:
            frame["client_msg_id"] = client_msg_id
        await self.send(text_data=json.dumps(frame))

    def _reject_log_allowed(self) -> bool:
        now = monotonic()
        if (
            self._reject_count == 0
            or now - self._reject_window_start >= REJECT_LOG_WINDOW_S
        ):
            self._reject_window_start = now
            self._reject_count = 0
        self._reject_count += 1
        if self._reject_count == REJECT_LOG_MAX + 1:
            log.warning(
                "herodraft_chat_rejections_throttled",
                system="herodraft",
                subsystem="chat",
                draft_id=self.draft_id,
                user_id=self._chat_user_id(),
                window_s=REJECT_LOG_WINDOW_S,
            )
        return self._reject_count <= REJECT_LOG_MAX

    def _log_chat_rejected(self, code: ChatErrorCode, **extra: Any) -> None:
        if not self._reject_log_allowed():
            return
        log.info(
            "herodraft_chat_rejected",
            system="herodraft",
            subsystem="chat",
            draft_id=self.draft_id,
            user_id=self._chat_user_id(),
            code=code,
            **extra,
        )

    async def _handle_chat(self, msg_type: str, data: dict[str, Any]) -> None:
        client_msg_id = data.get("client_msg_id")
        if client_msg_id is not None and not (
            isinstance(client_msg_id, str) and _CLIENT_MSG_ID.fullmatch(client_msg_id)
        ):
            self._log_chat_rejected("bad_request")
            await self._send_chat_error("bad_request", None)
            return
        try:
            result = await self._authorize_and_post(msg_type, data)
        except ChatError as e:
            self._log_chat_rejected(e.code)
            await self._send_chat_error(e.code, client_msg_id)
            return
        except Exception as e:
            log.error(
                "herodraft_chat_rejected",
                system="herodraft",
                subsystem="chat",
                draft_id=self.draft_id,
                user_id=self._chat_user_id(),
                code="unavailable",
                error_type=type(e).__name__,
                exc_info=True,
            )
            await self._send_chat_error("unavailable", client_msg_id)
            return

        try:
            await self._publish_chat(result)
        except Exception as e:
            # Stored already: telling the client "not sent" would invite a duplicate.
            log.error(
                "herodraft_chat_publish_failed",
                system="herodraft",
                subsystem="chat",
                draft_id=self.draft_id,
                user_id=self._chat_user_id(),
                channel=result.channel,
                error_type=type(e).__name__,
                exc_info=True,
            )
            await self.send(
                text_data=json.dumps(
                    {"type": "chat_message", "message": result.message}
                )
            )
        ack: dict[str, Any] = {"type": "chat_ack", "id": result.message["id"]}
        if client_msg_id is not None:
            ack["client_msg_id"] = client_msg_id
        await self.send(text_data=json.dumps(ack))
        sent: dict[str, Any] = {
            "draft_id": self.draft_id,
            "user_id": self._chat_user_id(),
            "channel": result.channel,
            "length": len(result.message["body"]),
        }
        if result.channel == "all":
            sent["kind"] = result.message["kind"]
        log.info("herodraft_chat_sent", system="herodraft", subsystem="chat", **sent)

    async def _publish_chat(self, result: PostResult) -> None:
        if result.channel == "team" and result.team_id is not None:
            await self.channel_layer.group_send(
                team_group_name(self.draft_id, result.team_id),
                {
                    "type": "herodraft.chat_team",
                    "team_id": result.team_id,
                    "message": result.message,
                },
            )
        else:
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "herodraft.chat_all", "message": result.message},
            )

    async def _recover_chat_viewer(self) -> None:
        try:
            viewer = await self._resolve_chat_viewer()
        except Exception as e:
            await self._chat_bootstrap_failed(e)
            return
        await self._regroup(viewer)

    async def _authorize_and_post(
        self, msg_type: str, data: dict[str, Any]
    ) -> PostResult:
        user_id = self._chat_user_id()
        if user_id is not None and self._chat_degraded:
            await sync_to_async(check_rate_limit, thread_sensitive=False)(
                self.draft_id, user_id
            )
            await self._recover_chat_viewer()
            if self._chat_degraded:
                raise ChatError("unavailable")
            authorize_post(self._chat_viewer)
        else:
            authorize_post(self._chat_viewer)
            if user_id is None:
                raise ChatError("not_participant")
            await sync_to_async(check_rate_limit, thread_sensitive=False)(
                self.draft_id, user_id
            )
        viewer, outcome = await self._post_chat(msg_type, data)
        if self._viewer_changed(self._chat_viewer, viewer):
            await self._regroup(viewer)
        else:
            self._chat_viewer = viewer
        if isinstance(outcome, ChatError):
            raise outcome
        return outcome

    async def _apply_chat_viewer(self, viewer: ChatViewer) -> None:
        wanted = (
            team_group_name(self.draft_id, viewer.team_id)
            if viewer.role == "member" and viewer.team_id is not None
            else None
        )
        for group in tuple(self._extra_groups):
            if group != wanted:
                await self.channel_layer.group_discard(group, self.channel_name)
                self._extra_groups.discard(group)
        if wanted is not None and wanted not in self._extra_groups:
            await self.channel_layer.group_add(wanted, self.channel_name)
            self._extra_groups.add(wanted)
        self._chat_viewer = viewer
        self._chat_verified_at = None

    async def _send_chat_history(self) -> None:
        viewer = self._chat_viewer
        messages = await self._chat_history_messages(viewer)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat_history",
                    "viewer": viewer.as_payload(),
                    "messages": messages,
                }
            )
        )
        self._chat_degraded = False

    async def _chat_bootstrap_failed(self, error: Exception) -> None:
        user_id = self._chat_user_id()
        log.error(
            "herodraft_chat_bootstrap_failed",
            system="herodraft",
            subsystem="chat",
            draft_id=self.draft_id,
            user_id=user_id,
            error_type=type(error).__name__,
            exc_info=True,
        )
        # Fail closed but keep team groups: each team frame re-checks, so the next one can recover.
        self._chat_viewer = ChatViewer(
            user_id=user_id, team_id=None, role="spectator", joined_at=None
        )
        self._chat_verified_at = None
        if self._chat_degraded:
            return
        self._chat_degraded = True
        try:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "chat_error",
                        "code": "unavailable",
                        "viewer": self._chat_viewer.as_payload(),
                    }
                )
            )
        except Exception as e:
            log.error(
                "herodraft_chat_bootstrap_failed",
                system="herodraft",
                subsystem="chat",
                draft_id=self.draft_id,
                user_id=user_id,
                stage="notify",
                error_type=type(e).__name__,
                exc_info=True,
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

    async def receive(
        self, text_data: str | None = None, bytes_data: bytes | None = None
    ) -> None:
        """Handle incoming WebSocket messages from clients.

        Chat frames are accepted from any socket and authorised per message;
        everything else is processed only for captains. Each message runs in a
        `ws.message` span via `traced_message`.
        """
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            if not self._reject_log_allowed():
                return
            log.warning(
                "ws_malformed_message",
                system="herodraft",
                subsystem="connection",
                draft_id=self.draft_id,
                user_id=getattr(self.user, "id", None),
            )
            return
        msg_type = data.get("type") if isinstance(data, dict) else None
        if not isinstance(msg_type, str):
            msg_type = "unknown"

        if msg_type in _CHAT_MESSAGE_TYPES:
            async with self.traced_message(msg_type):
                await self._handle_chat(msg_type, data)
            return

        if not self._is_captain:
            return
        async with self.traced_message(msg_type):
            if msg_type == "heartbeat":
                await self.handle_heartbeat()

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
                    # Reconnect = an earlier captain_connected in this draft, read
                    # before this event is written. The frontend's "joined" vs
                    # "reconnected" toast relies on it; the server owns history.
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

                    # Pause only in DRAFTING (timers running, picks matter);
                    # pausing in RESUMING would allow an infinite-time exploit.
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
        # Omit missing/None fields instead of .get()-ing them: null fails Zod's
        # .optional(), which accepts undefined only.
        message = {
            "type": "herodraft_event",
            "event_type": event.get("event_type"),
        }
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
        if event.get("event_type") in CHAT_RESYNC_EVENTS:
            await self._resync_after_draft_event(event.get("chat_roster"))

    async def herodraft_chat_all(self, event: dict[str, Any]) -> None:
        await self.send(
            text_data=json.dumps({"type": "chat_message", "message": event["message"]})
        )

    async def herodraft_chat_team(self, event: dict[str, Any]) -> None:
        team_id = event.get("team_id")
        if not isinstance(team_id, int) or isinstance(team_id, bool):
            return
        if team_group_name(self.draft_id, team_id) not in self._extra_groups:
            return
        viewer = self._recently_verified_member(team_id)
        if viewer is not None:
            # The roster check is cached; a logout must still stop delivery at once.
            try:
                alive = await self._chat_session_alive()
            except Exception:
                alive = False
            if not alive:
                viewer = None
        if viewer is None:
            try:
                viewer = await self._resolve_chat_viewer()
            except Exception as e:
                await self._chat_bootstrap_failed(e)
                return
        if viewer.role != "member" or viewer.team_id != team_id:
            log.info(
                "herodraft_chat_delivery_revoked",
                system="herodraft",
                subsystem="chat",
                draft_id=self.draft_id,
                user_id=self._chat_user_id(),
                team_id=team_id,
                role=viewer.role,
            )
            await self._regroup(viewer)
            return
        if self._viewer_changed(self._chat_viewer, viewer):
            # Recovering from a failed lookup: the fresh history already holds this message.
            await self._regroup(viewer)
            return
        self._chat_viewer = viewer
        self._chat_verified_at = monotonic()
        message = event["message"]
        if _created_before(message, viewer.joined_at):
            return
        await self.send(
            text_data=json.dumps({"type": "chat_message", "message": message})
        )

    def _recently_verified_member(self, team_id: int) -> ChatViewer | None:
        viewer = self._chat_viewer
        checked = self._chat_verified_at
        if (
            self._chat_degraded
            or checked is None
            or viewer.role != "member"
            or viewer.team_id != team_id
            or monotonic() - checked >= CHAT_DELIVERY_CACHE_S
        ):
            return None
        return viewer

    async def herodraft_chat_resync(self, event: dict[str, Any]) -> None:
        self._chat_verified_at = None
        user_id = self._chat_user_id()
        if user_id is None:
            return
        team_ids = event.get("team_ids") or []
        user_ids = event.get("user_ids") or []
        in_team_group = any(
            team_group_name(self.draft_id, t) in self._extra_groups
            for t in team_ids
            if isinstance(t, int)
        )
        if user_id in user_ids or in_team_group:
            await self._chat_resync()

    async def _resync_after_draft_event(self, chat_roster: Any) -> None:
        self._chat_verified_at = None
        user_id = self._chat_user_id()
        if user_id is None:
            return
        if not self._extra_groups:
            try:
                roster = (
                    chat_roster
                    if isinstance(chat_roster, list)
                    else await self._draft_roster_user_ids()
                )
            except Exception as e:
                log.warning(
                    "herodraft_chat_resync_roster_failed",
                    system="herodraft",
                    subsystem="chat",
                    draft_id=self.draft_id,
                    user_id=user_id,
                    error_type=type(e).__name__,
                )
                return
            if user_id not in roster:
                return
        await self._chat_resync()

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
