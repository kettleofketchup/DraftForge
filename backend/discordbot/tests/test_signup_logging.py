"""Integration tests for the signup-flow log sequence.

These tests would have caught the original "user told ok but no EventSignup row"
bug:
  - TransactionTestCase so transaction.on_commit hooks actually fire
  - setUp creates a CustomUser + OrgUser + complete PlayerDotaProfile so the
    handler takes the direct-signup path (not needs_modal)
  - Assert on DB row existence, not just log presence
  - Assert required log events present (Task 12 adds ordering invariants)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TransactionTestCase
from django.utils import timezone
from structlog.contextvars import clear_contextvars
from structlog.testing import capture_logs

from app.models import CustomUser, GameType, Organization
from discordbot.components import SignupButton
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.services import resolve_or_create_org_user
from org.models_profiles import PlayerDotaProfile


def _mock_interaction(event_id, *, interaction_id=12345, user_id=67890):
    interaction = MagicMock()
    interaction.id = interaction_id
    interaction.user.id = user_id
    interaction.user.name = "testuser"
    interaction.channel_id = 111
    interaction.guild_id = 222
    interaction.type = MagicMock()
    interaction.type.name = "component"
    interaction.data = {"custom_id": f"event_signup:{event_id}"}
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


class SignupButtonHappyPathTests(TransactionTestCase):
    """SignupButton happy path: profile complete -> direct signup -> DB row + log chain."""

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Test Event",
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=False,  # disable Celery dispatch noise for this test
        )
        self.user = CustomUser.objects.create(username="testuser", discordId="67890")
        org_user = resolve_or_create_org_user(self.user, self.org)
        # Complete Dota profile so handle_signup_button takes the direct-signup path
        PlayerDotaProfile.objects.create(
            org_user=org_user,
            pos_1=True,
            rank_status="active",
            rank_medal="Archon 3",
        )

    def tearDown(self):
        clear_contextvars()

    def test_callback_creates_eventsignup_and_emits_log_chain(self):
        button = SignupButton(self.event.pk)
        interaction = _mock_interaction(self.event.pk)

        with capture_logs() as logs, \
             patch("discordbot.components.respond_to_signup_user", new=AsyncMock()):
            asyncio.run(button.callback(interaction))

        # 1. DB-state assertion - this is what catches the silent-signup bug
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1,
            "Expected exactly one EventSignup row after direct signup",
        )
        signup = EventSignup.objects.get(event=self.event, user=self.user)
        self.assertIn(signup.status, [SignupStatus.RSVP, SignupStatus.APPROVED, SignupStatus.CONFIRMED, SignupStatus.PENDING_APPROVAL])

        # 2. Log-chain assertion - required events present, with correlation
        events = [log["event"] for log in logs]
        required = ["interaction_started", "handler_invoked", "interaction_finished"]
        for event in required:
            self.assertIn(event, events, f"missing event: {event}; got: {events}")

        # 3. Bookend logs carry interaction_id (explicit fields, not contextvar-derived)
        started = next(log for log in logs if log["event"] == "interaction_started")
        finished = next(log for log in logs if log["event"] == "interaction_finished")
        self.assertEqual(started["interaction_id"], "12345")
        self.assertEqual(finished["interaction_id"], "12345")
        self.assertEqual(finished["outcome"], "signed_up")
        self.assertEqual(finished["tags_csv"], "events,signup")
