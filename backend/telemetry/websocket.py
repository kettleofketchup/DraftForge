"""WebSocket telemetry mixin for Django Channels consumers."""

import uuid
from typing import Any, Optional

import structlog

from telemetry.labels import extract_labels
from telemetry.logging import get_logger

log = get_logger(__name__)


class TelemetryConsumerMixin:
    """
    Mixin for Django Channels consumers that provides telemetry context.

    Add to your consumer class:
        class DraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
            async def connect(self):
                await self.telemetry_connect()
                await super().connect()

            async def disconnect(self, close_code):
                await self.telemetry_disconnect(close_code)
                await super().disconnect(close_code)

    Features:
    - Generates unique connection ID (ws_conn_id)
    - Extracts labels from WebSocket path
    - Binds context for all logs during connection
    - Logs connect/disconnect events
    """

    # These will be set during connect
    ws_conn_id: str
    ws_labels: dict[str, Any]

    # Expected to be provided by the consumer class
    scope: dict[str, Any]

    async def telemetry_connect(self) -> None:
        """
        Initialize telemetry context for WebSocket connection.

        Call this at the start of your connect() method.
        """
        # Generate connection ID
        self.ws_conn_id = str(uuid.uuid4())

        # Extract labels from WebSocket path
        # Convert /ws/draft/5/ to match our label patterns
        path = self.scope.get("path", "")
        self.ws_labels = extract_labels(path)

        # Get user info if authenticated
        user = self.scope.get("user")
        user_id: Optional[int] = None
        if user and getattr(user, "is_authenticated", False):
            user_id = user.pk

        # Get client info
        client = self.scope.get("client", ("unknown", 0))
        client_ip = client[0] if client else "unknown"

        # Build context
        context: dict[str, Any] = {
            "ws.conn_id": self.ws_conn_id,
            **self.ws_labels,
        }
        if user_id is not None:
            context["user.id"] = user_id

        # Bind context to structlog
        structlog.contextvars.bind_contextvars(**context)

        # Log connection
        log.info("ws_connected", client_ip=client_ip)

    async def telemetry_disconnect(self, close_code: int) -> None:
        """
        Clean up telemetry context for WebSocket disconnection.

        Call this at the start of your disconnect() method.

        Args:
            close_code: WebSocket close code
        """
        log.info("ws_disconnected", close_code=close_code)

        # Clear context
        structlog.contextvars.clear_contextvars()

    async def telemetry_receive(self, text_data: Optional[str] = None) -> None:
        """
        Log received WebSocket message.

        Call this at the start of your receive() method if you want to log messages.

        Args:
            text_data: The received text data (truncated in logs)
        """
        # Log with truncated data to avoid huge log entries
        preview = text_data[:100] if text_data else None
        log.debug("ws_receive", data_preview=preview)
