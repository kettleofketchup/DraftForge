"""
Base WebSocket consumer for draft-related connections.

Provides shared infrastructure for heartbeat processing, captain tracking,
connection counting, and server-side ping keepalive.

# OpenTelemetry tracing

Key lifecycle methods (connect, disconnect, heartbeat, captain register/
unregister) are wrapped in OTel spans so each WebSocket operation shows
up in Tempo as its own trace. Spans share `ws.conn_id` as an attribute,
so you can find every operation for a given session by querying spans
on that key — even though each operation is its own independent trace.

We do NOT wrap `connect→disconnect` in a single long-lived parent span:
OTel only exports spans on `End()`, so a 30-min WS session would show
nothing in Tempo until disconnect, and a process crash mid-session
would lose the whole trace. Short spans per operation export
immediately and survive crashes.

Logs emitted inside a span automatically get `trace_id` / `span_id`
attributes (via `telemetry.logging._add_otel_trace_context`). The
Loki datasource's `traceID` derived field turns those into clickable
links to the Tempo trace view.

Subclasses that want to trace their own per-message handlers should
use `BaseDraftConsumer.traced_message(message_type, **attrs)` as an
async context manager — see its docstring for details.
"""

import asyncio
import contextlib
import json
import time
from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import redis
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Model
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from app.tasks import draft_tick
from app.tasks import herodraft_tick as legacy_tick  # late lookup keeps patches working
from app.tasks.draft_tick import (
    CAPTAIN_CHANNEL_TTL,
    HEARTBEAT_TTL,
    TickDriver,
    captain_channel_key,
    heartbeat_key,
)
from telemetry.logging import get_logger
from telemetry.websocket import TelemetryConsumerMixin

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Server-side ping interval in seconds (must be < frontend staleTimeoutMs)
# ~16 bytes per message; 100 connections = ~1.6 KB/s — negligible
PING_INTERVAL = 1


class BaseDraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    """Abstract base class for draft WebSocket consumers.

    Provides shared infrastructure:
    - Heartbeat processing from captains
    - Captain channel registration in Redis (for kick detection)
    - Connection count tracking in Redis (for tick broadcaster)
    - Server-side ping loop to keep connections alive during pauses
    - Telemetry integration

    Subclasses must implement abstract methods to provide draft-specific behavior.
    """

    PING_ENABLED: bool = True
    kick_duplicate_captain_connections: bool = False
    clear_heartbeat_on_disconnect: bool = True

    # --- Abstract methods subclasses must implement ---

    @abstractmethod
    def get_room_group_prefix(self) -> str:
        """Return the channel layer group prefix (e.g. 'herodraft')."""
        ...

    @abstractmethod
    async def draft_exists(self, draft_id: int) -> bool:
        """Check if the draft with the given ID exists."""
        ...

    @abstractmethod
    async def get_initial_state_data(self, draft_id: int) -> dict | None:
        """Return serialized draft state for initial_state message, or None."""
        ...

    @abstractmethod
    async def get_captain_draft_team(
        self, draft_id: int, user: "AbstractBaseUser"
    ) -> Model | None:
        """Return the DraftTeam for this captain, or None if not a captain."""
        ...

    @abstractmethod
    def get_active_draft_state_values(self) -> list[str]:
        """Return state values where the tick broadcaster should run.

        Example: [HeroDraftState.DRAFTING.value, HeroDraftState.RESUMING.value]
        """
        ...

    async def on_captain_state_change(
        self, draft_id: int, user: "AbstractBaseUser", is_connected: bool
    ) -> None:
        """Hook called when a captain connects/disconnects.

        Override in subclasses to handle pause-on-disconnect, event logging,
        and state broadcasting. Default is a no-op.
        """
        pass

    def get_redis_prefix(self) -> str:
        return self.get_room_group_prefix()

    def get_tick_driver(self) -> TickDriver | None:
        return None

    def should_start_tick_broadcaster(self, initial_state: dict | None) -> bool:
        return bool(initial_state) and (
            initial_state.get("state") in self.get_active_draft_state_values()
        )

    async def send_initial_messages(self, initial_state: dict | None) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_state",
                    "draft_state": initial_state,
                }
            )
        )

    # --- Redis helpers ---

    def _redis(self) -> redis.Redis:
        return legacy_tick.get_redis_client()

    def _heartbeat_key(self, draft_id: int, user_id: int) -> str:
        return heartbeat_key(self.get_redis_prefix(), draft_id, user_id)

    def _captain_channel_key(self, draft_id: int, user_id: int) -> str:
        return captain_channel_key(self.get_redis_prefix(), draft_id, user_id)

    # --- Kick detection ---

    async def _get_existing_captain_channel(self) -> str | None:
        """Get the existing captain channel from Redis, if any."""
        channel_key = self._captain_channel_key(self.draft_id, self.user.id)
        return self._redis().get(channel_key)

    async def _kick_channel(self, old_channel: str) -> None:
        """Send kick message to an existing captain connection."""
        log.info(
            "captain_kicked",
            system="websocket",
            subsystem="connection",
            draft_id=self.draft_id,
            user_id=self.user.id,
            old_channel=old_channel,
            new_channel=self.channel_name,
        )
        try:
            await self.channel_layer.send(
                old_channel,
                {
                    "type": f"{self.get_room_group_prefix()}.kicked",
                    "reason": "new_connection",
                },
            )
        except Exception as e:
            log.warning(
                "captain_kick_failed",
                system="websocket",
                subsystem="connection",
                draft_id=self.draft_id,
                user_id=self.user.id,
                old_channel=old_channel,
                error=str(e),
            )

    # --- Heartbeat ---

    async def handle_heartbeat(self) -> None:
        """Process a heartbeat message from a captain. Updates Redis TTL."""
        with tracer.start_as_current_span(
            "ws.heartbeat",
            attributes=self._base_span_attrs(),
        ) as span:
            r = self._redis()
            r.set(
                self._heartbeat_key(self.draft_id, self.user.id),
                str(time.time()),
                ex=HEARTBEAT_TTL,
            )
            span.set_attribute("ws.heartbeat_ttl_s", HEARTBEAT_TTL)
            log.debug(
                "heartbeat_received",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                user_id=self.user.id,
                ttl=HEARTBEAT_TTL,
            )

    # --- Captain channel registration ---

    async def _register_captain(self) -> None:
        """Register this connection as the captain's active channel in Redis."""
        with tracer.start_as_current_span(
            "ws.captain_register",
            attributes=self._base_span_attrs(),
        ):
            r = self._redis()
            channel_key = self._captain_channel_key(self.draft_id, self.user.id)
            r.set(channel_key, self.channel_name, ex=CAPTAIN_CHANNEL_TTL)
            # Initialize heartbeat (nested span)
            await self.handle_heartbeat()
            log.info(
                "captain_registered",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                user_id=self.user.id,
                channel=self.channel_name,
            )

    async def _unregister_captain_if_current(self) -> None:
        """Unregister captain channel only if it's still this connection."""
        with tracer.start_as_current_span(
            "ws.captain_unregister",
            attributes=self._base_span_attrs(),
        ) as span:
            r = self._redis()
            channel_key = self._captain_channel_key(self.draft_id, self.user.id)

            current_channel = r.get(channel_key)
            if current_channel == self.channel_name:
                r.delete(channel_key)
                if self.clear_heartbeat_on_disconnect:
                    r.delete(self._heartbeat_key(self.draft_id, self.user.id))
                span.set_attribute("ws.captain_unregistered", True)
                log.info(
                    "captain_unregistered",
                    system="websocket",
                    subsystem="heartbeat",
                    draft_id=self.draft_id,
                    user_id=self.user.id,
                )
            else:
                # Another connection has taken over; nothing to clean up
                # for this connection. Tag so trace shows the no-op.
                span.set_attribute("ws.captain_unregistered", False)
                span.set_attribute("ws.skipped_reason", "not_current_channel")

    # --- Connection count tracking ---

    @database_sync_to_async
    def _increment_connection_count(self) -> None:
        """Increment WebSocket connection count in Redis."""
        try:
            draft_tick.increment_connection_count(
                self.get_redis_prefix(), self.draft_id
            )
            self._connection_tracked = True
        except Exception as e:
            log.warning(
                "connection_count_increment_failed",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                error=str(e),
            )

    @database_sync_to_async
    def _decrement_connection_count(self) -> None:
        """Decrement WebSocket connection count in Redis."""
        try:
            draft_tick.decrement_connection_count(
                self.get_redis_prefix(), self.draft_id
            )
            self._connection_tracked = False
        except Exception as e:
            log.warning(
                "connection_count_decrement_failed",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                error=str(e),
            )

    # --- Tick broadcaster ---

    @database_sync_to_async
    def _maybe_start_tick_broadcaster(self) -> None:
        """Start tick broadcaster if not already running."""
        try:
            driver = self.get_tick_driver()
            if driver is None:
                legacy_tick.start_tick_broadcaster(self.draft_id)
            else:
                draft_tick.start_tick_broadcaster(driver, self.draft_id)
        except Exception as e:
            log.warning(
                "tick_broadcaster_start_failed",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                error=str(e),
            )

    # --- Server-side ping loop ---

    async def _ping_loop(self) -> None:
        """Send periodic ping messages to keep WebSocket connections alive.

        This prevents proxies/load balancers from closing idle connections,
        especially during PAUSED state when no tick messages are being sent.
        """
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                await self.send(text_data=json.dumps({"type": "ping"}))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug(
                "ping_loop_ended",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                error=str(e),
            )

    # --- Span helpers ---

    def _base_span_attrs(self) -> dict[str, Any]:
        """Attributes attached to every WS-lifecycle span.

        Pulled into its own helper because Tempo correlation works by
        attribute (we don't share a parent span across operations) —
        every span MUST carry `ws.conn_id` so a Tempo query like
        `{.ws.conn_id="abc..."}` finds the whole session. Missing this
        on even one span breaks the correlation path.
        """
        attrs: dict[str, Any] = {
            "ws.consumer": self.__class__.__name__,
        }
        # `ws_conn_id` is set by TelemetryConsumerMixin.telemetry_connect;
        # base_connect() may invoke a heartbeat span before that runs in
        # error paths, so guard.
        conn_id = getattr(self, "ws_conn_id", None)
        if conn_id:
            attrs["ws.conn_id"] = conn_id
        draft_id = getattr(self, "draft_id", None)
        if draft_id is not None:
            attrs["ws.draft_id"] = draft_id
        user = getattr(self, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            attrs["user.id"] = user.pk
        return attrs

    @contextlib.asynccontextmanager
    async def traced_message(
        self, message_type: str, **extra_attrs: Any
    ) -> AsyncIterator[Span]:
        """Async context manager for tracing a received WS message.

        Subclasses that handle messages should wrap their per-message
        logic with this so each message becomes a `ws.message` span in
        Tempo. Logs inside the block automatically get the trace_id.

        Usage in a subclass's `receive` / `receive_json`::

            async def receive(self, text_data=None, **kwargs):
                msg = json.loads(text_data)
                async with self.traced_message(msg.get("type", "unknown"),
                                               **{"ws.event": msg.get("event")}):
                    # subclass-specific handler logic
                    ...

        Exceptions propagate normally. OTel's `start_as_current_span`
        auto-records exceptions and sets the span status to ERROR on
        context exit (record_exception=True, set_status_on_exception=True
        are SDK defaults), so we don't need to do it manually.
        """
        attrs = self._base_span_attrs()
        attrs["ws.message_type"] = message_type
        attrs.update(extra_attrs)
        with tracer.start_as_current_span("ws.message", attributes=attrs) as span:
            yield span

    # TEMP-DIAG
    async def dispatch(self, message: dict[str, Any]) -> None:
        from channels.db import aclose_old_connections
        from channels.consumer import get_handler_name

        mtype = message.get("type")
        t0 = time.monotonic()
        t1 = t0
        try:
            handler = getattr(self, get_handler_name(message), None)
            await aclose_old_connections()
            t1 = time.monotonic()
            if handler is None:
                raise ValueError(f"No handler for message type {mtype}")
            await handler(message)
        finally:
            dt = time.monotonic() - t0
            if mtype not in ("draft.tick",) or dt > 0.3:
                log.debug(
                    "diag_dispatch",
                    system="websocket",
                    subsystem="diag",
                    draft_id=getattr(self, "draft_id", None),
                    channel_name=self.channel_name,
                    msg_type=mtype,
                    duration_ms=round(dt * 1000, 1),
                    close_conn_wait_ms=round((t1 - t0) * 1000, 1),
                )
            if mtype == "draft.tick":
                log.debug(
                    "diag_tick_recv",
                    system="websocket",
                    subsystem="diag",
                    draft_id=getattr(self, "draft_id", None),
                    channel_name=self.channel_name,
                    duration_ms=round(dt * 1000, 1),
                )

    # --- Base connect/disconnect ---

    async def base_connect(self) -> bool:
        """Shared connection setup. Call from subclass connect() after any
        subclass-specific pre-connection logic (e.g. kick detection).

        Sets up: draft_id, room_group_name, user, validates draft, joins group,
        accepts connection, tracks connection, sends initial state, registers
        captain, marks captain connected, starts tick broadcaster if active.
        """
        await self.telemetry_connect()

        self.draft_id = int(self.scope["url_route"]["kwargs"]["draft_id"])
        prefix = self.get_room_group_prefix()
        self.room_group_name = f"{prefix}_{self.draft_id}"
        self.user = self.scope.get("user")
        self._connection_tracked = False
        self._is_captain = False
        self._ping_task = None

        if (
            self.kick_duplicate_captain_connections
            and self.user
            and self.user.is_authenticated
        ):
            existing_channel = await self._get_existing_captain_channel()
            if existing_channel and existing_channel != self.channel_name:
                await self._kick_channel(existing_channel)

        with tracer.start_as_current_span(
            "ws.connect",
            attributes={
                **self._base_span_attrs(),
                "ws.path": self.scope.get("path", ""),
            },
        ) as span:
            # OTel's start_as_current_span auto-records propagating
            # exceptions and sets ERROR status on context exit, so no
            # outer try/except is needed here. The inner try/except for
            # initial_state catches + returns False instead of raising,
            # so it has to set the status manually.

            # Validate draft exists
            exists = await self.draft_exists(self.draft_id)
            if not exists:
                span.set_attribute("ws.connect_outcome", "draft_not_found")
                log.warning(
                    "draft_not_found",
                    system="websocket",
                    subsystem="heartbeat",
                    draft_id=self.draft_id,
                    reason="closing connection",
                )
                await self.close()
                return False

            # Check if this user is a captain
            if self.user and self.user.is_authenticated:
                draft_team = await self.get_captain_draft_team(self.draft_id, self.user)
                if draft_team is not None:
                    self._is_captain = True
            span.set_attribute("ws.is_captain", self._is_captain)

            # Join room group
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            log.debug(  # TEMP-DIAG
                "diag_group_add",
                system="websocket",
                subsystem="diag",
                draft_id=self.draft_id,
                channel_name=self.channel_name,
                user_id=getattr(self.user, "id", None),
            )
            await self.accept()

            # Track connection count
            await self._increment_connection_count()

            # Register captain's channel for future kick detection
            # (nested span — ws.captain_register)
            if self._is_captain:
                await self._register_captain()

            # Send initial state
            try:
                initial_state = await self.get_initial_state_data(self.draft_id)
                await self.send_initial_messages(initial_state)

                if self.should_start_tick_broadcaster(initial_state):
                    await self._maybe_start_tick_broadcaster()

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, "initial_state_failed"))
                log.error(
                    "initial_state_send_failed",
                    system="websocket",
                    subsystem="heartbeat",
                    draft_id=self.draft_id,
                    error=str(e),
                )
                await self.close()
                return False

            # Notify subclass of captain connection state
            if self._is_captain:
                await self.on_captain_state_change(self.draft_id, self.user, True)

            # Start server-side ping loop
            if self.PING_ENABLED:
                self._ping_task = asyncio.ensure_future(self._ping_loop())

            span.set_attribute("ws.connect_outcome", "ok")
            return True

    async def base_disconnect(self, close_code: int | None) -> None:
        """Shared disconnection cleanup. Call from subclass disconnect().

        Handles: cancel ping, kicked connections, decrement count, unregister
        captain, mark disconnected, leave group, telemetry.
        """
        with tracer.start_as_current_span(
            "ws.disconnect",
            attributes={
                **self._base_span_attrs(),
                "ws.close_code": close_code if close_code is not None else -1,
            },
        ) as span:
            await self.telemetry_disconnect(close_code)

            # Cancel ping loop and wait for clean shutdown
            if getattr(self, "_ping_task", None):
                self._ping_task.cancel()
                try:
                    await self._ping_task
                except asyncio.CancelledError:
                    pass
                self._ping_task = None

            # Track disconnection
            if hasattr(self, "_connection_tracked") and self._connection_tracked:
                await self._decrement_connection_count()

            # If this connection was kicked by a new connection, don't mark as disconnected
            was_kicked = getattr(self, "_was_kicked", False)
            if was_kicked:
                span.set_attribute("ws.kicked", True)
                log.info(
                    "kicked_disconnect_skipped",
                    system="websocket",
                    subsystem="heartbeat",
                    draft_id=getattr(self, "draft_id", None),
                    user_id=getattr(getattr(self, "user", None), "id", None),
                )
                if hasattr(self, "room_group_name"):
                    await self.channel_layer.group_discard(
                        self.room_group_name, self.channel_name
                    )
                return

            # Clean up captain channel registration and mark as disconnected
            # (nested span — ws.captain_unregister)
            if (
                hasattr(self, "_is_captain")
                and self._is_captain
                and hasattr(self, "user")
                and hasattr(self, "draft_id")
            ):
                try:
                    await self._unregister_captain_if_current()
                    await self.on_captain_state_change(self.draft_id, self.user, False)
                except Exception as e:
                    # Don't mark the whole disconnect as ERROR — cleanup
                    # failure is recoverable. Record the exception so
                    # Tempo shows what failed.
                    span.record_exception(e)
                    log.error(
                        "captain_disconnect_cleanup_failed",
                        system="websocket",
                        subsystem="heartbeat",
                        draft_id=self.draft_id,
                        error=str(e),
                    )

            # Leave room group
            if hasattr(self, "room_group_name"):
                await self.channel_layer.group_discard(
                    self.room_group_name, self.channel_name
                )
                log.debug(  # TEMP-DIAG
                    "diag_group_discard",
                    system="websocket",
                    subsystem="diag",
                    draft_id=getattr(self, "draft_id", None),
                    channel_name=self.channel_name,
                )
