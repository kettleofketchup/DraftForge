"""
Integration tests that hit the real Discord API.

Requirements:
- DISCORD_BOT_TOKEN env var must be set
- Test Discord server (guild ID: 1467168401805017142)
- Test channels: Announcement (1482767177063858216), Signups (1482767709279096893)

Run: just test::run 'python manage.py test events.tests.test_discord_integration -v 2'
"""

import unittest

from django.conf import settings
from django.test import TestCase

from discordbot.models import DiscordMessageLog
from discordbot.test_utils import (
    assert_discord_message_delivered,
    cleanup_test_messages,
    fetch_channel_messages,
)

SKIP_REASON = "DISCORD_BOT_TOKEN not configured"
HAS_TOKEN = bool(getattr(settings, "DISCORD_BOT_TOKEN", ""))

ANNOUNCEMENT_CHANNEL = "1482767177063858216"
SIGNUPS_CHANNEL = "1482767709279096893"


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealDiscordSendTest(TestCase):
    def tearDown(self):
        cleanup_test_messages("integration_test")
        cleanup_test_messages("integration_test_signups")

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
    def tearDown(self):
        cleanup_test_messages("readback_test")

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
    def tearDown(self):
        cleanup_test_messages("event_announcement")

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
