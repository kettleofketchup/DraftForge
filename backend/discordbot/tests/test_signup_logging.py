"""Integration tests for the Discord signup-flow log + persistence chain.

Pins three invariants of the signup pipeline:
  - the handler takes the direct-signup path when the OrgUser profile is
    complete (no needs_modal),
  - ``transaction.on_commit`` hooks actually fire (hence TransactionTestCase),
  - the chain produces both an ``EventSignup`` row AND the ordered log
    sequence the dashboards depend on.

The bot calls the signup handler through an internal HTTP wrapper
(``signup_actions.signup_button``). To exercise the full in-process log
chain without standing up a real HTTP server, ``_patch_signup_button_inproc``
swaps the wrapper for the canonical handler in the namespace the bot looks
it up from.
"""

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TransactionTestCase
from django.utils import timezone
from structlog.contextvars import clear_contextvars
from structlog.testing import capture_logs

from app.models import CustomUser, GameType, Organization
from discordbot.components import SignupButton
from events.constants import EventState, SignupStatus
from events.discord.handlers import handle_signup_button
from events.models import Event, EventSignup
from events.services import resolve_or_create_org_user
from org.models_profiles import PlayerDotaProfile


def _patch_signup_button_inproc():
    """Route ``signup_button`` calls to the in-process handler.

    Patches the binding ``discordbot.components`` actually looks up at call
    time (module-top import), so every callback path that uses the wrapper
    resolves to ``handle_signup_button`` instead of the HTTP client.

    Returns an ``ExitStack`` so callers can stack additional patches and
    exit them together with ``with stack:``.
    """
    stack = ExitStack()
    stack.enter_context(
        patch(
            "discordbot.components.signup_button",
            side_effect=handle_signup_button,
        )
    )
    return stack


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

        with _patch_signup_button_inproc(), \
             capture_logs() as logs, \
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


class FullSignupPipelineTests(TransactionTestCase):
    """End-to-end: button click -> DB row -> on_commit hook -> embed-update dispatch.

    Uses TransactionTestCase so transaction.on_commit hooks actually fire.
    """

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Test Event",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=True,
            discord_announcement_channel_id="9999999",
        )
        self.user = CustomUser.objects.create(username="testuser", discordId="67890")
        org_user = resolve_or_create_org_user(self.user, self.org)
        PlayerDotaProfile.objects.create(
            org_user=org_user, pos_1=True, rank_status="active", rank_medal="Archon 3",
        )

    def tearDown(self):
        clear_contextvars()

    def test_emits_complete_ordered_sequence_with_signup_persisted(self):
        button = SignupButton(self.event.pk)
        interaction = _mock_interaction(self.event.pk)

        with _patch_signup_button_inproc(), \
             capture_logs() as logs, \
             patch("events.tasks.send_signup_update.delay") as mock_delay, \
             patch("discordbot.components.respond_to_signup_user", new=AsyncMock()):
            asyncio.run(button.callback(interaction))

        # DB-state - the canonical assertion
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1,
        )
        signup = EventSignup.objects.get(event=self.event, user=self.user)

        events = [log["event"] for log in logs]
        required = [
            "interaction_started",
            "handler_invoked",
            "process_rsvp_started",
            "signup_post_commit_hooks_scheduled",
            "embed_update_queued",
            "signup_created",
            "interaction_finished",
        ]
        for event in required:
            self.assertIn(event, events, f"missing: {event}; got: {events}")

        # Ordering invariants
        self.assertLess(events.index("interaction_started"), events.index("handler_invoked"))
        self.assertLess(events.index("handler_invoked"), events.index("process_rsvp_started"))
        self.assertLess(events.index("process_rsvp_started"), events.index("signup_post_commit_hooks_scheduled"))
        self.assertLess(events.index("signup_post_commit_hooks_scheduled"), events.index("embed_update_queued"))
        self.assertLess(events.index("embed_update_queued"), events.index("signup_created"))
        self.assertLess(events.index("signup_created"), events.index("interaction_finished"))

        # signup_id correlation - cross-check user_id and status
        signup_created = next(log for log in logs if log["event"] == "signup_created")
        self.assertEqual(signup_created["signup_id"], signup.pk)
        persisted = EventSignup.objects.get(pk=signup_created["signup_id"])
        self.assertEqual(persisted.user_id, self.user.pk)
        self.assertEqual(persisted.status, signup_created["status"])

        # interaction_finished
        finished = next(log for log in logs if log["event"] == "interaction_finished")
        self.assertEqual(finished["outcome"], "signed_up")
        self.assertEqual(finished["interaction_id"], "12345")
        self.assertEqual(finished["tags_csv"], "events,signup")

        # Celery dispatch fires EXACTLY ONCE per signup (Task 8 Step 7 dedupe fix)
        mock_delay.assert_called_once_with(self.event.pk, interaction_id="12345")


class CeleryHopTests(TransactionTestCase):
    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Test Event",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=True,
            discord_announcement_channel_id="9999999",
        )

    def tearDown(self):
        clear_contextvars()

    def test_celery_task_rebinds_interaction_id_from_kwargs(self):
        from events.tasks import send_signup_update

        with capture_logs() as logs, \
             patch("events.tasks.get_event_for_task", return_value=None):
            send_signup_update.apply(args=[self.event.pk], kwargs={"interaction_id": "abc123"})

        started = [log for log in logs if log["event"] == "celery_task_started"]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["interaction_id"], "abc123")
        self.assertEqual(started[0]["task"], "send_signup_update")
        self.assertEqual(started[0]["event_id"], self.event.pk)

        # After I2 fix, celery_task_finished now fires on early-return paths too
        finished = [log for log in logs if log["event"] == "celery_task_finished"]
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["interaction_id"], "abc123")

    def test_celery_task_body_failure_emits_celery_task_failed(self):
        from events.tasks import send_signup_update

        with capture_logs() as logs, \
             patch("events.tasks.get_event_for_task", side_effect=RuntimeError("discord 500")), \
             self.assertRaises(RuntimeError):
            send_signup_update.apply(
                args=[self.event.pk],
                kwargs={"interaction_id": "abc123"},
                throw=True,
            )

        failed = [log for log in logs if log["event"] == "celery_task_failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["error_type"], "RuntimeError")
        self.assertEqual(failed[0]["interaction_id"], "abc123")


class DispatchSkippedBranchTests(TransactionTestCase):
    """notify_signup_changed must log embed_update_skipped (not queued) when flags off."""

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org, name="No Announce",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=False,
        )

    def tearDown(self):
        clear_contextvars()

    def test_logs_skipped_when_discord_announcement_disabled(self):
        from events.discord.dispatch import notify_signup_changed

        with capture_logs() as logs, \
             patch("events.tasks.send_signup_update.delay") as mock_delay:
            notify_signup_changed(self.event)

        skipped = [log for log in logs if log["event"] == "embed_update_skipped"]
        queued = [log for log in logs if log["event"] == "embed_update_queued"]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["reason"], "discord_announcement_disabled")
        self.assertEqual(len(queued), 0)
        mock_delay.assert_not_called()


class SignupsClosedFailurePathTests(TransactionTestCase):
    """When signups are closed, handler returns error early; CM closes outcome=error.

    Note: this exercises the `event.state != SIGNUPS_OPEN` early-return,
    NOT the `_get_org_user` failure path. See GetOrgUserNullPathTests for that.
    """

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        # Use UPCOMING (signups not yet open) since handler checks
        # `event.state != EventState.SIGNUPS_OPEN`.
        self.event = Event.objects.create(
            organization=self.org, name="Closed",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.UPCOMING,
            discord_announcement=False,
        )

    def tearDown(self):
        clear_contextvars()

    def test_signups_closed_emits_outcome_error_no_signup_id(self):
        button = SignupButton(self.event.pk)
        interaction = _mock_interaction(self.event.pk)

        with _patch_signup_button_inproc(), \
             capture_logs() as logs, \
             patch("discordbot.components.respond_to_signup_user", new=AsyncMock()):
            asyncio.run(button.callback(interaction))

        self.assertEqual(EventSignup.objects.filter(event=self.event).count(), 0)
        finished = next(log for log in logs if log["event"] == "interaction_finished")
        self.assertEqual(finished["outcome"], "error")
        self.assertNotIn("signup_id", finished)


class GetOrgUserNullPathTests(TransactionTestCase):
    """Force _get_org_user to return (None, None); handler returns error."""

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org, name="Open Event",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=False,
        )

    def tearDown(self):
        clear_contextvars()

    def test_get_org_user_null_emits_outcome_error(self):
        button = SignupButton(self.event.pk)
        interaction = _mock_interaction(self.event.pk)

        with _patch_signup_button_inproc(), \
             capture_logs() as logs, \
             patch("events.discord.handlers._get_org_user", return_value=(None, None)), \
             patch("discordbot.components.respond_to_signup_user", new=AsyncMock()):
            asyncio.run(button.callback(interaction))

        finished = next(log for log in logs if log["event"] == "interaction_finished")
        self.assertEqual(finished["outcome"], "error")
        self.assertNotIn("org_user_id", finished)
        self.assertEqual(EventSignup.objects.filter(event=self.event).count(), 0)


class RollbackPathTests(TransactionTestCase):
    """If the signup transaction rolls back, on_commit hooks must NOT fire."""

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org, name="Rollback Test",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=True,
            discord_announcement_channel_id="9999999",
        )
        self.user = CustomUser.objects.create(username="rollback_user", discordId="67892")
        org_user = resolve_or_create_org_user(self.user, self.org)
        PlayerDotaProfile.objects.create(
            org_user=org_user, pos_1=True, rank_status="active", rank_medal="Archon 3",
        )

    def tearDown(self):
        clear_contextvars()

    def test_rollback_skips_embed_update_queued(self):
        from django.db import transaction
        from events.services import process_rsvp

        with capture_logs() as logs, \
             patch("events.tasks.send_signup_update.delay") as mock_delay:
            try:
                with transaction.atomic():
                    process_rsvp(self.event, self.user)
                    raise RuntimeError("force rollback after process_rsvp")
            except RuntimeError:
                pass

        events = [log["event"] for log in logs]
        self.assertIn("process_rsvp_started", events)
        self.assertIn("signup_post_commit_hooks_scheduled", events)
        self.assertNotIn("embed_update_queued", events)
        self.assertNotIn("signup_created", events)  # New: deferred to on_commit, suppressed on rollback
        mock_delay.assert_not_called()
        self.assertEqual(EventSignup.objects.filter(event=self.event, user=self.user).count(), 0)


class ConcurrentCMTests(TransactionTestCase):
    """Two concurrent discord_log_context blocks must not bleed contextvars."""

    def setUp(self):
        clear_contextvars()

    def tearDown(self):
        clear_contextvars()

    def test_concurrent_cms_isolate_contextvars(self):
        from discordbot.log_context import discord_log_context

        async def run_one(interaction_id, custom_id):
            interaction = MagicMock()
            interaction.id = interaction_id
            interaction.user.id = 67890
            interaction.user.name = "tester"
            interaction.channel_id = 111
            interaction.guild_id = 222
            interaction.type = MagicMock()
            interaction.type.name = "component"
            interaction.data = {"custom_id": custom_id}
            captured = {}
            async with discord_log_context(interaction, custom_id=custom_id):
                from structlog.contextvars import get_contextvars
                captured = dict(get_contextvars())
            return captured

        async def both():
            return await asyncio.gather(
                run_one(11111, "event_signup:1"),
                run_one(22222, "event_signup:2"),
            )

        a, b = asyncio.run(both())
        self.assertEqual(a["interaction_id"], "11111")
        self.assertEqual(b["interaction_id"], "22222")
        self.assertEqual(a["event_id"], 1)
        self.assertEqual(b["event_id"], 2)


class DMContextEdgeCaseTests(TransactionTestCase):
    """guild_id=None (DM context) must not crash the CM."""

    def setUp(self):
        clear_contextvars()
        self.org = Organization.objects.create(name="Test Org")
        self.event = Event.objects.create(
            organization=self.org, name="DM Test",
            scheduled_at=timezone.now(),
            game_type=GameType.DOTA2,
            state=EventState.SIGNUPS_OPEN,
            discord_announcement=False,
        )
        self.user = CustomUser.objects.create(username="dmuser", discordId="67891")
        org_user = resolve_or_create_org_user(self.user, self.org)
        PlayerDotaProfile.objects.create(
            org_user=org_user, pos_1=True, rank_status="active", rank_medal="Archon 3",
        )

    def tearDown(self):
        clear_contextvars()

    def test_dm_context_no_guild_id_completes_successfully(self):
        button = SignupButton(self.event.pk)
        interaction = _mock_interaction(self.event.pk, user_id=67891)
        interaction.guild_id = None
        interaction.channel_id = None

        with _patch_signup_button_inproc(), \
             capture_logs() as logs, \
             patch("discordbot.components.respond_to_signup_user", new=AsyncMock()):
            asyncio.run(button.callback(interaction))

        finished = next(log for log in logs if log["event"] == "interaction_finished")
        self.assertIsNone(finished["guild_id"])
        self.assertIsNone(finished["channel_id"])
        self.assertEqual(finished["outcome"], "signed_up")
