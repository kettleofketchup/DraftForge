"""Tests for WebSocket telemetry mixin."""

import asyncio
from unittest import TestCase
from unittest.mock import MagicMock

import structlog

from telemetry.websocket import TelemetryConsumerMixin


class MockConsumer(TelemetryConsumerMixin):
    """Mock consumer for testing."""

    def __init__(self):
        self.scope = {
            "path": "/ws/draft/5/",
            "user": MagicMock(),
            "client": ("127.0.0.1", 12345),
        }
        self.scope["user"].is_authenticated = True
        self.scope["user"].pk = 42
        self.channel_layer = MagicMock()
        self.channel_name = "test_channel"


class TelemetryConsumerMixinTest(TestCase):
    """Tests for TelemetryConsumerMixin."""

    def setUp(self):
        """Reset structlog state."""
        structlog.contextvars.clear_contextvars()

    def tearDown(self):
        """Clean up."""
        structlog.contextvars.clear_contextvars()

    def test_connect_generates_connection_id(self):
        """Connect generates ws_conn_id."""
        consumer = MockConsumer()
        asyncio.run(consumer.telemetry_connect())
        self.assertIsNotNone(consumer.ws_conn_id)
        self.assertIsInstance(consumer.ws_conn_id, str)

    def test_connect_extracts_labels(self):
        """Connect extracts labels from WebSocket path."""
        consumer = MockConsumer()
        asyncio.run(consumer.telemetry_connect())
        self.assertEqual(consumer.ws_labels["labels"], ["draft"])
        self.assertEqual(consumer.ws_labels["draft.id"], 5)

    def test_connect_binds_user_context(self):
        """Connect binds user context when authenticated."""
        consumer = MockConsumer()

        async def run_test():
            await consumer.telemetry_connect()
            ctx = structlog.contextvars.get_contextvars()
            return ctx

        ctx = asyncio.run(run_test())
        self.assertEqual(ctx.get("user.id"), 42)

    def test_disconnect_clears_context(self):
        """Disconnect clears structlog context."""
        consumer = MockConsumer()

        async def run_test():
            await consumer.telemetry_connect()
            await consumer.telemetry_disconnect(1000)

        asyncio.run(run_test())

        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("ws.conn_id", ctx)
