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
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from telemetry.logging import get_logger
from telemetry.websocket import TelemetryConsumerMixin

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Heartbeat expires after 30 seconds without renewal
HEARTBEAT_TTL = 30

# Captain channel registration expires after 5 minutes (cleanup on crash)
CAPTAIN_CHANNEL_TTL = 300

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
    async def get_captain_draft_team(self, draft_id: int, user):
        """Return the DraftTeam for this captain, or None if not a captain."""
        ...

    @abstractmethod
    def get_active_draft_state_values(self) -> list[str]:
        """Return state values where the tick broadcaster should run.

        Example: [HeroDraftState.DRAFTING.value, HeroDraftState.RESUMING.value]
        """
        ...

    async def on_captain_state_change(self, draft_id, user, is_connected):
        """Hook called when a captain connects/disconnects.

        Override in subclasses to handle pause-on-disconnect, event logging,
        and state broadcasting. Default is a no-op.
        """
        pass

    # --- Redis key helpers ---

    def _heartbeat_key(self, draft_id: int, user_id: int) -> str:
        prefix = self.get_room_group_prefix()
        return f"{prefix}:{draft_id}:captain:{user_id}:heartbeat"

    def _captain_channel_key(self, draft_id: int, user_id: int) -> str:
        prefix = self.get_room_group_prefix()
        return f"{prefix}:{draft_id}:captain:{user_id}:channel"

    # --- Heartbeat ---

    async def handle_heartbeat(self):
        """Process a heartbeat message from a captain. Updates Redis TTL."""
        with tracer.start_as_current_span(
            "ws.heartbeat",
            attributes=self._base_span_attrs(),
        ) as span:
            from app.tasks.herodraft_tick import get_redis_client

            r = get_redis_client()
            heartbeat_key = self._heartbeat_key(self.draft_id, self.user.id)
            r.set(heartbeat_key, str(time.time()), ex=HEARTBEAT_TTL)
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

    async def _register_captain(self):
        """Register this connection as the captain's active channel in Redis."""
        with tracer.start_as_current_span(
            "ws.captain_register",
            attributes=self._base_span_attrs(),
        ):
            from app.tasks.herodraft_tick import get_redis_client

            r = get_redis_client()
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

    async def _unregister_captain_if_current(self):
        """Unregister captain channel only if it's still this connection."""
        with tracer.start_as_current_span(
            "ws.captain_unregister",
            attributes=self._base_span_attrs(),
        ) as span:
            from app.tasks.herodraft_tick import get_redis_client

            r = get_redis_client()
            channel_key = self._captain_channel_key(self.draft_id, self.user.id)
            heartbeat_key = self._heartbeat_key(self.draft_id, self.user.id)

            current_channel = r.get(channel_key)
            if current_channel == self.channel_name:
                r.delete(channel_key)
                r.delete(heartbeat_key)
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
    def _increment_connection_count(self):
        """Increment WebSocket connection count in Redis."""
        from app.tasks.herodraft_tick import increment_connection_count

        try:
            increment_connection_count(self.draft_id)
            self._connection_tracked = True
        except Exception as e:
            log.warning(
                f"Failed to increment connection for draft {self.draft_id}: {e}"
            )

    @database_sync_to_async
    def _decrement_connection_count(self):
        """Decrement WebSocket connection count in Redis."""
        from app.tasks.herodraft_tick import decrement_connection_count

        try:
            decrement_connection_count(self.draft_id)
            self._connection_tracked = False
        except Exception as e:
            log.warning(
                f"Failed to decrement connection for draft {self.draft_id}: {e}"
            )

    # --- Tick broadcaster ---

    @database_sync_to_async
    def _maybe_start_tick_broadcaster(self):
        """Start tick broadcaster if not already running."""
        from app.tasks.herodraft_tick import start_tick_broadcaster

        try:
            start_tick_broadcaster(self.draft_id)
        except Exception as e:
            log.warning(
                f"Failed to start tick broadcaster for draft {self.draft_id}: {e}"
            )

    # --- Server-side ping loop ---

    async def _ping_loop(self):
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
            log.debug(f"Ping loop ended for draft {self.draft_id}: {e}")

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
    async def traced_message(self, message_type: str, **extra_attrs: Any):
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

    # --- Base connect/disconnect ---

    async def base_connect(self):
        """Shared connection setup. Call from subclass connect() after any
        subclass-specific pre-connection logic (e.g. kick detection).

        Sets up: draft_id, room_group_name, user, validates draft, joins group,
        accepts connection, tracks connection, sends initial state, registers
        captain, marks captain connected, starts tick broadcaster if active.
        """
        await self.telemetry_connect()

        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        prefix = self.get_room_group_prefix()
        self.room_group_name = f"{prefix}_{self.draft_id}"
        self.user = self.scope.get("user")
        self._connection_tracked = False
        self._is_captain = False
        self._ping_task = None

        with tracer.start_as_current_span(
            "ws.connect",
            attributes={**self._base_span_attrs(), "ws.path": self.scope.get("path", "")},
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
                log.warning(f"{prefix} {self.draft_id} not found, closing connection")
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
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "initial_state",
                            "draft_state": initial_state,
                        }
                    )
                )

                # Start tick broadcaster if draft is in an active state
                if (
                    initial_state
                    and initial_state.get("state") in self.get_active_draft_state_values()
                ):
                    await self._maybe_start_tick_broadcaster()

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, "initial_state_failed"))
                log.error(f"Failed to send initial state for {prefix} {self.draft_id}: {e}")
                await self.close()
                return False

            # Notify subclass of captain connection state
            if self._is_captain:
                await self.on_captain_state_change(self.draft_id, self.user, True)

            # Start server-side ping loop
            self._ping_task = asyncio.ensure_future(self._ping_loop())

            span.set_attribute("ws.connect_outcome", "ok")
            return True

    async def base_disconnect(self, close_code):
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
                    f"Skipping disconnect handling for kicked connection "
                    f"(user {getattr(self, 'user', None)}, draft {getattr(self, 'draft_id', None)})"
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
                        f"Failed to mark captain disconnected for draft {self.draft_id}: {e}"
                    )

            # Leave room group
            if hasattr(self, "room_group_name"):
                await self.channel_layer.group_discard(
                    self.room_group_name, self.channel_name
                )
