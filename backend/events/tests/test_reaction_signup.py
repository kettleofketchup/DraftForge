"""Tests for Discord reaction → EventSignup flow."""

from unittest.mock import patch

from django.test import TestCase

from discordbot.models import DiscordMessageLog
from events.constants import EventState, SignupStatus
from events.discord import handle_reaction_cancel, handle_reaction_signup
from events.models import EventSignup
from events.tests.base import EventTestCase


class HandleReactionSignupTest(EventTestCase):
    """Test handle_reaction_signup() — the direct handler (no Discord API)."""

    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.auto_approve = True
        self.event.save()

        # Simulate an announcement message log entry
        self.log_entry = DiscordMessageLog.objects.create(
            channel_id="1482767177063858216",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=self.event.pk,
            discord_message_id="999888777",
            success=True,
        )
        # Give the test user a discord ID
        self.user.discordId = "100000000000000001"
        self.user.save()

    def test_creates_signup_on_checkmark_reaction(self):
        success, detail = handle_reaction_signup("999888777", "100000000000000001")
        self.assertTrue(success)
        self.assertTrue(
            EventSignup.objects.filter(event=self.event, user=self.user).exists()
        )

    def test_returns_signup_status(self):
        success, detail = handle_reaction_signup("999888777", "100000000000000001")
        self.assertTrue(success)
        # Returns the resulting signup status (varies based on requirements)
        valid_statuses = [s.value for s in SignupStatus]
        self.assertIn(detail, valid_statuses)

    def test_skips_unknown_message(self):
        success, detail = handle_reaction_signup("000000000", "100000000000000001")
        self.assertFalse(success)
        self.assertEqual(detail, "not_event_message")

    def test_skips_unlinked_discord_user(self):
        success, detail = handle_reaction_signup("999888777", "999999999999999999")
        self.assertFalse(success)
        self.assertEqual(detail, "user_not_linked")

    def test_skips_duplicate_signup(self):
        handle_reaction_signup("999888777", "100000000000000001")
        success, detail = handle_reaction_signup("999888777", "100000000000000001")
        self.assertFalse(success)
        self.assertIn("already", detail.lower())

    def test_skips_closed_event(self):
        self.event.state = EventState.COMPLETED
        self.event.save()
        success, detail = handle_reaction_signup("999888777", "100000000000000001")
        self.assertFalse(success)
        self.assertIn("not accepting", detail.lower())


class HandleReactionCancelTest(EventTestCase):
    """Test handle_reaction_cancel() — cancel signup via reaction."""

    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.auto_approve = True
        self.event.save()

        self.log_entry = DiscordMessageLog.objects.create(
            channel_id="1482767177063858216",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=self.event.pk,
            discord_message_id="999888777",
            success=True,
        )
        self.user.discordId = "100000000000000001"
        self.user.save()

    def test_cancels_existing_signup(self):
        # First sign up
        handle_reaction_signup("999888777", "100000000000000001")
        self.assertTrue(
            EventSignup.objects.filter(event=self.event, user=self.user).exists()
        )

        # Then cancel
        success, detail = handle_reaction_cancel("999888777", "100000000000000001")
        self.assertTrue(success)
        self.assertEqual(detail, "cancelled")

        signup = EventSignup.objects.get(event=self.event, user=self.user)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

    def test_skips_when_no_signup_exists(self):
        success, detail = handle_reaction_cancel("999888777", "100000000000000001")
        self.assertFalse(success)
        self.assertEqual(detail, "no_signup")

    def test_skips_unknown_message(self):
        success, detail = handle_reaction_cancel("000000000", "100000000000000001")
        self.assertFalse(success)
        self.assertEqual(detail, "not_event_message")
