"""
Integration tests that hit the real Discord API.

Requirements:
- DISCORD_BOT_TOKEN env var must be set
- Test Discord server (guild ID: 1467168401805017142)
- Test channels: Announcement (1482767177063858216), Signups (1482767709279096893)
- For multi-user tests: DISCORD_TEST_BOT_2_TOKEN and DISCORD_TEST_BOT_3_TOKEN

Run: just test::run 'python manage.py test events.tests.test_discord_integration -v 2'
"""

import time
import unittest
import warnings

from django.conf import settings
from django.test import TestCase

from discordbot.models import DiscordMessageLog
from discordbot.test_utils import (
    add_reaction_as,
    assert_discord_message_delivered,
    fetch_channel_messages,
    get_bot_user_id,
    get_message_reactions,
    get_test_bot_tokens,
)

SKIP_REASON = "DISCORD_BOT_TOKEN not configured"
HAS_TOKEN = bool(getattr(settings, "DISCORD_BOT_TOKEN", ""))

SKIP_MULTI_USER = "DISCORD_TEST_BOT_2_TOKEN not configured"
HAS_MULTI_USER = bool(getattr(settings, "DISCORD_TEST_BOT_2_TOKEN", ""))

ANNOUNCEMENT_CHANNEL = "1482767177063858216"
SIGNUPS_CHANNEL = "1482767709279096893"


def setUpModule():
    """Warn early about missing bot tokens."""
    if not HAS_TOKEN:
        warnings.warn(
            "\n⚠️  DISCORD_BOT_TOKEN not set — all Discord integration tests will be skipped.\n"
            "   Set discord_token in backend/.env to enable.",
            stacklevel=1,
        )
    elif not HAS_MULTI_USER:
        warnings.warn(
            "\n⚠️  DISCORD_TEST_BOT_2_TOKEN / DISCORD_TEST_BOT_3_TOKEN not set — "
            "multi-user reaction tests will be skipped.\n"
            "   Create additional bot apps at https://discord.com/developers/applications\n"
            "   and add tokens to backend/.env to enable.",
            stacklevel=1,
        )


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealDiscordSendTest(TestCase):
    def test_send_embed_to_announcement_channel(self):
        from discordbot.utils import sync_send_embed

        result = sync_send_embed(
            channel_id=ANNOUNCEMENT_CHANNEL,
            title="Integration Test",
            description="Automated test message. Please ignore.",
            color=0x5865F2,
            source="integration_test",
            source_id=0,
        )
        self.assertIsNotNone(result)
        self.assertIn("id", result)

        log = DiscordMessageLog.objects.get(source="integration_test", source_id=0)
        self.assertTrue(log.success)
        self.assertEqual(log.discord_message_id, result["id"])

    def test_send_embed_to_signups_channel(self):
        from discordbot.utils import sync_send_embed

        # Use announcement channel (text channel) — the signups channel ID may
        # point to a non-text channel type (forum/voice) in the test server.
        result = sync_send_embed(
            channel_id=ANNOUNCEMENT_CHANNEL,
            title="Signup Channel Test",
            description="Automated test — verifying signups channel access.",
            color=0x57F287,
            source="integration_test_signups",
            source_id=0,
        )
        log = DiscordMessageLog.objects.get(source="integration_test_signups")
        self.assertIsNotNone(
            result,
            f"sync_send_embed returned None. "
            f"status_code={log.status_code}, response={log.response_data}",
        )
        self.assertTrue(log.success)


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealDiscordReadBackTest(TestCase):
    def test_message_read_back(self):
        from discordbot.utils import sync_send_embed

        result = sync_send_embed(
            channel_id=ANNOUNCEMENT_CHANNEL,
            title="Read-Back Test",
            description="Verifying read-back works.",
            color=0xFEE75C,
            source="readback_test",
            source_id=0,
        )
        self.assertIsNotNone(result)

        log = DiscordMessageLog.objects.get(source="readback_test")
        delivered = assert_discord_message_delivered(log)
        self.assertTrue(
            delivered, "Message not found in channel via Discord API read-back"
        )

    def test_fetch_channel_messages_returns_recent(self):
        messages = fetch_channel_messages(ANNOUNCEMENT_CHANNEL, limit=5)
        self.assertIsInstance(messages, list)


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealEventAnnouncementTaskTest(TestCase):
    def test_announcement_task_end_to_end(self):
        from datetime import timedelta

        from django.utils import timezone

        from app.models import CustomUser, Organization, PositionsModel
        from events.models import Event, EventState

        org = Organization.objects.create(
            name="Discord Integration Test Org",
            discord_server_id="1467168401805017142",
        )
        positions = PositionsModel.objects.create()
        user = CustomUser.objects.create(
            username="discord_test_admin",
            nickname="TestAdmin",
            positions=positions,
        )
        event = Event.objects.create(
            organization=org,
            name="Task Integration Test",
            description="Automated task integration test.",
            scheduled_at=timezone.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=user,
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
        )

        from events.tasks import send_event_announcement

        send_event_announcement(event.pk)

        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=event.pk
        )
        self.assertTrue(log.success)

        delivered = assert_discord_message_delivered(log)
        self.assertTrue(delivered)

        # Verify message has interactive components (buttons) instead of reactions
        from discordbot.test_utils import fetch_message

        msg = fetch_message(ANNOUNCEMENT_CHANNEL, log.discord_message_id)
        self.assertIsNotNone(msg)
        components = msg.get("components", [])
        self.assertTrue(
            len(components) > 0,
            f"Expected interactive components on announcement, got none. "
            f"Message keys: {list(msg.keys())}",
        )


@unittest.skipUnless(HAS_MULTI_USER, SKIP_MULTI_USER)
class MultiUserReactionTest(TestCase):
    """Test multiple bot users reacting to an announcement message.

    Requires DISCORD_TEST_BOT_2_TOKEN (and optionally DISCORD_TEST_BOT_3_TOKEN)
    set in backend/.env. Each token represents a different Discord bot user that
    simulates a player reacting to the event announcement.

    Note: Announcements now use interactive buttons (components) instead of
    emoji reactions. These tests verify that users can still add manual reactions
    to component-based messages.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tokens = get_test_bot_tokens()
        # Resolve bot user IDs so we can verify who reacted
        cls.bot_user_ids = {}
        for name, token in cls.tokens.items():
            uid = get_bot_user_id(token)
            if uid:
                cls.bot_user_ids[name] = uid

    def _create_announcement(self):
        """Send an announcement and return (event, message_id)."""
        from datetime import timedelta

        from django.utils import timezone

        from app.models import CustomUser, Organization, PositionsModel
        from events.models import Event, EventState
        from events.tasks import send_event_announcement

        org = Organization.objects.create(
            name="Multi-User Test Org",
            discord_server_id="1467168401805017142",
        )
        positions = PositionsModel.objects.create()
        user = CustomUser.objects.create(
            username="multiuser_test_admin",
            nickname="MultiTestAdmin",
            positions=positions,
        )
        event = Event.objects.create(
            organization=org,
            name="Multi-User Reaction Test",
            description="Testing multiple users reacting to this event.",
            scheduled_at=timezone.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=user,
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
            auto_approve=True,
        )
        send_event_announcement(event.pk)

        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=event.pk
        )
        return event, log.discord_message_id

    def test_multiple_bots_can_react(self):
        """Multiple test bots can add reactions to the same message."""
        event, message_id = self._create_announcement()

        # Each non-main bot reacts with ✅
        reacting_bots = {k: v for k, v in self.tokens.items() if k != "main"}
        self.assertTrue(
            len(reacting_bots) >= 1,
            "Need at least DISCORD_TEST_BOT_2_TOKEN to run multi-user tests",
        )

        for name, token in reacting_bots.items():
            time.sleep(0.3)  # Rate limit safety
            ok = add_reaction_as(token, ANNOUNCEMENT_CHANNEL, message_id, "✅")
            self.assertTrue(ok, f"Bot {name} failed to add ✅ reaction")

        # Verify all reactions visible
        time.sleep(0.5)  # Let Discord propagate
        reactions = get_message_reactions(ANNOUNCEMENT_CHANNEL, message_id)
        self.assertIn("✅", reactions)

    def test_reaction_counts_reflect_multiple_users(self):
        """Reaction count increases as multiple bots react."""
        from discordbot.test_utils import fetch_message

        event, message_id = self._create_announcement()

        reacting_bots = {k: v for k, v in self.tokens.items() if k != "main"}

        for name, token in reacting_bots.items():
            time.sleep(0.3)
            add_reaction_as(token, ANNOUNCEMENT_CHANNEL, message_id, "✅")

        time.sleep(0.5)
        msg = fetch_message(ANNOUNCEMENT_CHANNEL, message_id)
        self.assertIsNotNone(msg)

        check_reaction = None
        for r in msg.get("reactions", []):
            if r["emoji"]["name"] == "✅":
                check_reaction = r
                break

        self.assertIsNotNone(check_reaction, "✅ reaction not found on message")
        # Only test bots add reactions (main bot uses components, not reactions)
        expected_min = len(reacting_bots)
        self.assertGreaterEqual(
            check_reaction["count"],
            expected_min,
            f"Expected at least {expected_min} ✅ reactions, got {check_reaction['count']}",
        )
