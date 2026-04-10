"""
Base WebSocket consumer for draft-related connections.

Provides shared infrastructure for heartbeat processing, captain tracking,
connection counting, and server-side ping keepalive.
"""

import asyncio
import json
import time
from abc import abstractmethod

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from telemetry.logging import get_logger
from telemetry.websocket import TelemetryConsumerMixin

log = get_logger(__name__)

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
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        heartbeat_key = self._heartbeat_key(self.draft_id, self.user.id)
        r.set(heartbeat_key, str(time.time()), ex=HEARTBEAT_TTL)
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
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self._captain_channel_key(self.draft_id, self.user.id)
        r.set(channel_key, self.channel_name, ex=CAPTAIN_CHANNEL_TTL)
        # Initialize heartbeat
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
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self._captain_channel_key(self.draft_id, self.user.id)
        heartbeat_key = self._heartbeat_key(self.draft_id, self.user.id)

        current_channel = r.get(channel_key)
        if current_channel == self.channel_name:
            r.delete(channel_key)
            r.delete(heartbeat_key)
            log.info(
                "captain_unregistered",
                system="websocket",
                subsystem="heartbeat",
                draft_id=self.draft_id,
                user_id=self.user.id,
            )

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

        # Validate draft exists
        exists = await self.draft_exists(self.draft_id)
        if not exists:
            log.warning(f"{prefix} {self.draft_id} not found, closing connection")
            await self.close()
            return False

        # Check if this user is a captain
        if self.user and self.user.is_authenticated:
            draft_team = await self.get_captain_draft_team(self.draft_id, self.user)
            if draft_team is not None:
                self._is_captain = True

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Track connection count
        await self._increment_connection_count()

        # Register captain's channel for future kick detection
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
            log.error(f"Failed to send initial state for {prefix} {self.draft_id}: {e}")
            await self.close()
            return False

        # Notify subclass of captain connection state
        if self._is_captain:
            await self.on_captain_state_change(self.draft_id, self.user, True)

        # Start server-side ping loop
        self._ping_task = asyncio.ensure_future(self._ping_loop())

        return True

    async def base_disconnect(self, close_code):
        """Shared disconnection cleanup. Call from subclass disconnect().

        Handles: cancel ping, kicked connections, decrement count, unregister
        captain, mark disconnected, leave group, telemetry.
        """
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
                log.error(
                    f"Failed to mark captain disconnected for draft {self.draft_id}: {e}"
                )

        # Leave room group
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
