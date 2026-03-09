"""Unit tests for BaseDraftConsumer abstract class."""

from django.test import SimpleTestCase

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
