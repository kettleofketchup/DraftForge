"""Unit tests for BaseDraftConsumer abstract class."""

import asyncio
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.consumers_base import BaseDraftConsumer


class ConcreteDraftConsumer(BaseDraftConsumer):
    """Minimal concrete implementation for testing BaseDraftConsumer."""

    def get_room_group_prefix(self):
        return "testdraft"

    async def draft_exists(self, draft_id):
        return True

    async def get_initial_state_data(self, draft_id):
        return {"type": "initial_state", "state": "drafting", "draft_id": draft_id}

    async def get_captain_draft_team(self, draft_id, user):
        return None

    def get_active_draft_state_values(self):
        return ["drafting"]


class TestAbstractInterface(SimpleTestCase):
    """Test that BaseDraftConsumer declares its abstract interface correctly.

    Note: AsyncWebsocketConsumer's metaclass is not ABCMeta, so Python won't
    raise TypeError on instantiation of incomplete subclasses. Instead, we
    verify that the @abstractmethod decorator is applied to the expected methods.
    """

    EXPECTED_ABSTRACT_METHODS = [
        "get_room_group_prefix",
        "draft_exists",
        "get_initial_state_data",
        "get_captain_draft_team",
        "get_active_draft_state_values",
    ]

    def test_abstract_methods_are_declared(self):
        """All five required methods are marked @abstractmethod."""
        for name in self.EXPECTED_ABSTRACT_METHODS:
            method = getattr(BaseDraftConsumer, name)
            self.assertTrue(
                getattr(method, "__isabstractmethod__", False),
                f"{name} should be marked @abstractmethod",
            )

    def test_on_captain_state_change_is_not_abstract(self):
        """The hook method on_captain_state_change is a concrete no-op, not abstract."""
        method = getattr(BaseDraftConsumer, "on_captain_state_change")
        self.assertFalse(
            getattr(method, "__isabstractmethod__", False),
            "on_captain_state_change should NOT be abstract (it is a hook with a default no-op)",
        )

    def test_concrete_subclass_overrides_all_abstracts(self):
        """ConcreteDraftConsumer overrides every abstract method."""
        for name in self.EXPECTED_ABSTRACT_METHODS:
            method = getattr(ConcreteDraftConsumer, name)
            self.assertFalse(
                getattr(method, "__isabstractmethod__", False),
                f"ConcreteDraftConsumer.{name} should be a concrete override",
            )


class TestRedisKeyGeneration(SimpleTestCase):
    """Test Redis key helper methods on BaseDraftConsumer."""

    def setUp(self):
        self.consumer = ConcreteDraftConsumer.__new__(ConcreteDraftConsumer)

    def test_heartbeat_key_format(self):
        """_heartbeat_key returns '{prefix}:{draft_id}:captain:{user_id}:heartbeat'."""
        key = self.consumer._heartbeat_key(draft_id=42, user_id=7)
        self.assertEqual(key, "testdraft:42:captain:7:heartbeat")

    def test_captain_channel_key_format(self):
        """_captain_channel_key returns '{prefix}:{draft_id}:captain:{user_id}:channel'."""
        key = self.consumer._captain_channel_key(draft_id=42, user_id=7)
        self.assertEqual(key, "testdraft:42:captain:7:channel")

    def test_keys_use_prefix_from_get_room_group_prefix(self):
        """Keys incorporate the value returned by get_room_group_prefix()."""

        class CustomPrefixConsumer(ConcreteDraftConsumer):
            def get_room_group_prefix(self):
                return "herodraft"

        consumer = CustomPrefixConsumer.__new__(CustomPrefixConsumer)
        hb_key = consumer._heartbeat_key(draft_id=1, user_id=2)
        ch_key = consumer._captain_channel_key(draft_id=1, user_id=2)

        self.assertTrue(hb_key.startswith("herodraft:"))
        self.assertTrue(ch_key.startswith("herodraft:"))
        self.assertEqual(hb_key, "herodraft:1:captain:2:heartbeat")
        self.assertEqual(ch_key, "herodraft:1:captain:2:channel")

    def test_keys_differ_for_heartbeat_vs_channel(self):
        """Heartbeat and channel keys for the same draft/user are distinct."""
        hb_key = self.consumer._heartbeat_key(draft_id=1, user_id=1)
        ch_key = self.consumer._captain_channel_key(draft_id=1, user_id=1)
        self.assertNotEqual(hb_key, ch_key)

    def test_keys_differ_across_drafts(self):
        """Keys for different draft IDs are distinct."""
        key_a = self.consumer._heartbeat_key(draft_id=1, user_id=1)
        key_b = self.consumer._heartbeat_key(draft_id=2, user_id=1)
        self.assertNotEqual(key_a, key_b)

    def test_keys_differ_across_users(self):
        """Keys for different user IDs are distinct."""
        key_a = self.consumer._heartbeat_key(draft_id=1, user_id=1)
        key_b = self.consumer._heartbeat_key(draft_id=1, user_id=2)
        self.assertNotEqual(key_a, key_b)


class TestSpanInstrumentation(SimpleTestCase):
    """Verify lifecycle methods emit OTel spans with expected attributes.

    The dashboard's per-user/per-conn-id correlation relies on every
    span carrying `ws.conn_id`. A future refactor that drops that
    attribute would silently break Tempo lookups — this test catches
    that regression at the unit level.
    """

    @classmethod
    def setUpClass(cls):
        # OTel installs `set_tracer_provider` as a one-shot — once a
        # provider is set (e.g. by Django's app startup), subsequent
        # `set_tracer_provider` calls are no-ops with a warning. So we
        # piggyback on whatever's current: if it's a real
        # `TracerProvider`, attach our in-memory processor to it; if
        # it's the proxy (telemetry disabled in this test env), install
        # ours as the first real provider.
        super().setUpClass()
        cls.exporter = InMemorySpanExporter()
        cls.processor = SimpleSpanProcessor(cls.exporter)
        provider = trace.get_tracer_provider()
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(cls.processor)
        else:
            provider = TracerProvider()
            provider.add_span_processor(cls.processor)
            trace.set_tracer_provider(provider)

    def setUp(self):
        # Each test starts with a clean span buffer so assertions on
        # span counts don't see leftovers from previous tests.
        self.exporter.clear()
        self.consumer = ConcreteDraftConsumer()
        self.consumer.ws_conn_id = "test-conn-1234"
        self.consumer.draft_id = 42
        # Consumer code reads both `user.id` (Django auth API) and
        # `user.pk` depending on path — populate both.
        self.consumer.user = SimpleNamespace(is_authenticated=True, pk=99, id=99)

    def _spans_by_name(self, name):
        return [s for s in self.exporter.get_finished_spans() if s.name == name]

    def test_handle_heartbeat_emits_span_with_conn_id(self):
        """ws.heartbeat span carries ws.conn_id + ws.draft_id + user.id."""
        with mock.patch(
            "app.tasks.herodraft_tick.get_redis_client"
        ) as mock_get_redis:
            mock_get_redis.return_value = mock.MagicMock()
            asyncio.run(self.consumer.handle_heartbeat())

        spans = self._spans_by_name("ws.heartbeat")
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs["ws.conn_id"], "test-conn-1234")
        self.assertEqual(attrs["ws.draft_id"], 42)
        self.assertEqual(attrs["user.id"], 99)
        self.assertEqual(attrs["ws.consumer"], "ConcreteDraftConsumer")
        # heartbeat-specific
        self.assertIn("ws.heartbeat_ttl_s", attrs)

    def test_base_span_attrs_skips_missing_conn_id(self):
        """No conn_id set yet → attribute is absent, not None.

        OTel SpanAttributes don't accept None values. The early-error
        path in `base_connect` could fire a heartbeat span before
        `telemetry_connect` runs, so `_base_span_attrs` must defensively
        omit `ws.conn_id` when it isn't bound.
        """
        consumer = ConcreteDraftConsumer()
        attrs = consumer._base_span_attrs()
        self.assertNotIn("ws.conn_id", attrs)
        self.assertNotIn("ws.draft_id", attrs)
        # consumer class is the one universal attribute
        self.assertEqual(attrs["ws.consumer"], "ConcreteDraftConsumer")

    def test_traced_message_records_message_type(self):
        """traced_message wraps subclass receive handlers with ws.message."""

        async def run():
            async with self.consumer.traced_message(
                "captain_pick", **{"ws.event": "hero_selected"}
            ):
                pass

        asyncio.run(run())
        spans = self._spans_by_name("ws.message")
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs["ws.message_type"], "captain_pick")
        self.assertEqual(attrs["ws.event"], "hero_selected")
        self.assertEqual(attrs["ws.conn_id"], "test-conn-1234")

    def test_traced_message_records_exception(self):
        """Exceptions inside traced_message land on the span as errors."""

        async def run():
            async with self.consumer.traced_message("explode"):
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            asyncio.run(run())

        spans = self._spans_by_name("ws.message")
        self.assertEqual(len(spans), 1)
        # OTel SpanKind.STATUS_CODE.ERROR == 2
        self.assertEqual(spans[0].status.status_code.value, 2)
        # Exception event recorded
        exc_events = [e for e in spans[0].events if e.name == "exception"]
        self.assertEqual(len(exc_events), 1)
