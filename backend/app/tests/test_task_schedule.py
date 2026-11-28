import re
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from app.auth import InternalServiceUser
from app.models import CustomUser
from app.views.internal import sweep_stale_discord_leases
from discordbot.models import (
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DMType,
    SignupDeliveryStatus,
    SignupPostDeliveryState,
)
from discordbot.signup_delivery import BeginOutcome, begin_signup_attempt
from discordbot.utils import DISCORD_API_BASE
from draft.models import HeroDraft
from events.models import Event, EventRepeater
from events.signup_post_send import SignupRunOutcome, run_signup_post
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.base import EventTestCase
from events.tests.test_signup_post_independence import destination_pairs
from events.tests.test_signup_post_send import GUILD, PRIMARY, response
from org.models import Organization, OrgUser
from tournament.models import Game, Team, Tournament


class TaskScheduleEndpointTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(name="Schedule Test Org")
        # signup_reminder requires an event_repeater to be enabled (not misconfigured).
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Schedule Test Repeater",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        self.event = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Schedule Test Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_signup_reminder=True,
            discord_signup_reminder_hours=6,
            discord_confirm_attendance=True,
            discord_confirm_attendance_hours=3,
            discord_profile_reminder=True,
            discord_profile_reminder_hours=4,
            discord_announcement=True,
            discord_announcement_channel_id="123456",
            discord_create_event=True,
        )
        user = CustomUser.objects.create_user(
            username="schedule_test_admin",
            password="test",
            is_staff=True,
        )
        self.client.force_authenticate(user=user)

    def test_signup_only_update_is_available(self) -> None:
        for announcement in destination_pairs("announcement-channel")[:-1]:
            for signup_enabled in (True, False):
                with self.subTest(announcement=announcement, signup=signup_enabled):
                    self.event.discord_post_signups = signup_enabled
                    self.event.discord_post_signups_channel_id = "signup-channel"
                    self.event.discord_announcement = announcement[0]
                    self.event.discord_announcement_channel_id = announcement[1] or ""
                    self.event.save()
                    response = self.client.get(
                        f"/api/events/{self.event.pk}/task-schedule/"
                    )
                    self.assertEqual(response.status_code, 200)
                    tasks = {row["task"]: row for row in response.json()}
                    self.assertEqual(
                        tasks["signup_update"]["status"],
                        "ready" if signup_enabled else "disabled",
                    )
                    self.assertEqual(tasks["signup_update"]["can_fire"], signup_enabled)
                    self.assertFalse(tasks["announcement"]["can_fire"])

    def test_returns_task_list(self) -> None:
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)

    def test_includes_all_enabled_tasks(self) -> None:
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        task_names = [t["task"] for t in tasks]
        self.assertIn("announcement", task_names)
        # signup_reminder drives subscriber DMs; fired detection uses has_dms.
        self.assertIn("signup_reminder", task_names)
        self.assertIn("confirm_attendance", task_names)
        self.assertIn("profile_reminder", task_names)
        self.assertIn("scheduled_event", task_names)

    def test_includes_fires_at(self) -> None:
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        reminder = next(t for t in tasks if t["task"] == "signup_reminder")
        self.assertIn("fires_at", reminder)
        self.assertIsNotNone(reminder["fires_at"])

    def test_disabled_tasks_show_disabled(self) -> None:
        event = Event.objects.create(
            organization=self.org,
            name="Disabled Test",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_signup_reminder=False,
            discord_confirm_attendance=False,
            discord_profile_reminder=False,
            discord_announcement=False,
            discord_create_event=False,
        )
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        tasks = resp.json()
        for task in tasks:
            if task["task"] in (
                "signup_reminder",
                "confirm_attendance",
                "profile_reminder",
                "scheduled_event",
            ):
                self.assertEqual(
                    task["status"], "disabled", f"{task['task']} should be disabled"
                )

    def test_signup_reminder_description_names_series_subscribers(self) -> None:
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        row = next(t for t in resp.json() if t["task"] == "signup_reminder")
        self.assertEqual(
            row["description"],
            "DMs series subscribers who haven't signed up, 6h before event",
        )

    def test_signup_reminder_description_when_misconfigured(self) -> None:
        event = Event.objects.create(
            organization=self.org,
            event_repeater=None,
            name="Misconfigured Reminder Test",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_signup_reminder=True,
            discord_signup_reminder_hours=12,
        )
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        row = next(t for t in resp.json() if t["task"] == "signup_reminder")
        self.assertEqual(row["status"], "misconfigured")
        self.assertEqual(
            row["description"],
            "DMs series subscribers who haven't signed up, 12h before event",
        )

    def test_fired_tasks_detected(self) -> None:
        # signup_reminder fired status is driven by DiscordEventDM rows
        # (subscriber DMs sent), not DiscordMessageLog.

        user = CustomUser.objects.create_user(
            username="dm_recipient", password="x", discordId="999"
        )
        org_user = OrgUser.objects.create(user=user, organization=self.org)
        discord_event = DiscordEvent.objects.create(
            event=self.event, guild_id="guild123"
        )
        DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        reminder = next(t for t in tasks if t["task"] == "signup_reminder")
        self.assertEqual(reminder["status"], "fired")

    def test_announcement_misconfigured(self) -> None:
        """Announcement enabled but no channel ID → misconfigured."""

        event = Event.objects.create(
            organization=self.org,
            name="Misconfigured Test",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_announcement=True,
            discord_announcement_channel_id="",  # empty
        )
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        tasks = resp.json()
        ann = next(t for t in tasks if t["task"] == "announcement")
        self.assertEqual(ann["status"], "misconfigured")

    def _profile_reminder_row(self, event: Event) -> dict[str, Any]:
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        return next(t for t in resp.json() if t["task"] == "profile_reminder")

    def test_profile_reminder_misconfigured_without_channel(self) -> None:
        event = Event.objects.create(
            organization=self.org,
            name="Profile Reminder No Channel",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_profile_reminder=True,
            discord_profile_reminder_hours=4,
            discord_announcement=False,
            discord_announcement_channel_id="",
        )
        row = self._profile_reminder_row(event)
        self.assertEqual(row["status"], "misconfigured")
        self.assertFalse(row["can_fire"])
        self.assertIn("announcement channel", row["description"].lower())
        self.assertIsNone(re.search(r"\bDM", row["description"]))

    def test_profile_reminder_description_names_its_channel(self) -> None:
        row = self._profile_reminder_row(self.event)
        self.assertNotEqual(row["status"], "misconfigured")
        self.assertIn("its own channel", row["description"])
        self.assertIn("announcement channel", row["description"].lower())
        self.assertIn("4h", row["description"])
        self.assertIsNone(re.search(r"\bDM", row["description"]))

    def _row(self, event: Event, task: str) -> dict[str, Any]:
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        return next(t for t in resp.json() if t["task"] == task)

    def _own_channel_event(self, name: str, **fields: Any) -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_announcement=False,
            discord_announcement_channel_id="",
            **fields,
        )

    def test_confirm_attendance_enabled_with_only_own_channel(self) -> None:
        event = self._own_channel_event(
            "Attendance Own Channel",
            discord_confirm_attendance=True,
            discord_confirm_attendance_hours=3,
            discord_confirm_attendance_channel_id="777",
        )
        row = self._row(event, "confirm_attendance")
        self.assertNotIn(row["status"], ("misconfigured", "disabled"))
        self.assertIn("its own channel", row["description"])
        self.assertIn("3h", row["description"])

    def test_confirm_attendance_misconfigured_when_both_blank(self) -> None:
        event = self._own_channel_event(
            "Attendance No Channel", discord_confirm_attendance=True
        )
        row = self._row(event, "confirm_attendance")
        self.assertEqual(row["status"], "misconfigured")
        self.assertFalse(row["can_fire"])
        self.assertEqual(
            row["description"],
            "Enabled but no channel is set: pick one or set an announcement channel",
        )

    def test_profile_reminder_enabled_with_only_own_channel(self) -> None:
        event = self._own_channel_event(
            "Profile Own Channel",
            discord_profile_reminder=True,
            discord_profile_reminder_hours=4,
            discord_profile_reminder_channel_id="888",
        )
        row = self._profile_reminder_row(event)
        self.assertNotIn(row["status"], ("misconfigured", "disabled"))
        self.assertTrue(row["can_fire"])

    def test_profile_reminder_disabled_without_channel_is_not_misconfigured(
        self,
    ) -> None:
        event = Event.objects.create(
            organization=self.org,
            name="Profile Reminder Off",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_profile_reminder=False,
            discord_announcement_channel_id="",
        )
        row = self._profile_reminder_row(event)
        self.assertEqual(row["status"], "disabled")
        self.assertNotIn("Enabled", row["description"])
        self.assertNotIn("no channel is set", row["description"].lower())

    def test_profile_reminder_fired_with_channel_keeps_new_description(self) -> None:
        DiscordMessageLog.objects.create(
            source="profile_reminder",
            source_id=self.event.pk,
            success=True,
            channel_id="123456",
            embed_data={},
        )
        row = self._profile_reminder_row(self.event)
        self.assertEqual(row["status"], "fired")
        self.assertIn("announcement channel", row["description"].lower())

    def test_requires_authentication(self) -> None:
        client = APIClient()  # not authenticated
        resp = client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 403)

    def test_404_for_nonexistent_event(self) -> None:
        resp = self.client.get("/api/events/99999/task-schedule/")
        self.assertEqual(resp.status_code, 404)

    def test_signup_post_can_fire_when_already_fired(self) -> None:
        """signup_post (and announcement) must stay re-fireable so admin can
        repost when the Discord post was deleted or needs a refresh. Other
        tasks (one-shot DMs, reminders) stay non-fireable once fired.
        """

        # Mark signup_post as fired via DiscordEventLog (the gate used by
        # _task() to set status='fired' for signup_post).
        discord_event = DiscordEvent.objects.create(
            event=self.event, guild_id="guild_repost"
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="send_signup_post",
            success=True,
        )
        # Required gating: signup_post needs discord_post_signups + channel id.
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = "ch_signups"
        self.event.save()

        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        signup_post = next(t for t in tasks if t["task"] == "signup_post")
        self.assertEqual(signup_post["status"], "fired")
        self.assertTrue(
            signup_post["can_fire"],
            "signup_post must remain fireable after firing (Repost flow)",
        )


class FireSignupPostRepostTest(TestCase):
    """fire_event_task for signup_post must clear dedup state then dispatch
    send_event_announcement so the existing post is superseded by a fresh one.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(name="Repost Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Repost Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_announcement=True,
            discord_announcement_channel_id="ch_ann",
        )
        # Both is_staff and is_superuser bypass the org-admin cascade
        # (see has_org_admin_access in org/permissions.py).
        self.admin = CustomUser.objects.create_superuser(
            username="repost_admin", password="x"
        )
        self.client.force_authenticate(user=self.admin)

    def _seed_signup_post(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id="signup-channel",
            has_posted=True,
            message_id="old-message",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=self.event.pk,
            success=True,
            channel_id="signup-channel",
            embed_data={},
        )

    def test_signup_only_fire_and_repost_dispatch_shared_task(self) -> None:
        for announcement in destination_pairs("announcement-channel")[:-1]:
            for repost in (False, True):
                with self.subTest(announcement=announcement, repost=repost):
                    DiscordEventMsgSignup.objects.filter(event=self.event).delete()
                    DiscordMessageLog.objects.filter(source_id=self.event.pk).delete()
                    self.event.discord_post_signups = True
                    self.event.discord_post_signups_channel_id = "signup-channel"
                    self.event.discord_announcement = announcement[0]
                    self.event.discord_announcement_channel_id = announcement[1] or ""
                    self.event.save()
                    if repost:
                        self._seed_signup_post()
                    with patch("events.views.current_app") as app:
                        response = self.client.post(
                            f"/api/events/{self.event.pk}/task-schedule/signup_post/fire/"
                        )
                    self.assertEqual(response.status_code, 200, response.content)
                    app.send_task.assert_called_once_with(
                        "events.tasks.send_event_announcement",
                        args=[self.event.pk],
                        kwargs={
                            "generation": SignupPostDeliveryState.objects.get(
                                event=self.event
                            ).generation,
                            "manual": True,
                            "fired_by_user_id": self.admin.pk,
                        },
                    )
                    self.assertFalse(
                        DiscordEventMsgSignup.objects.filter(
                            event=self.event, has_posted=True
                        ).exists()
                    )
                    self.assertFalse(
                        DiscordMessageLog.objects.filter(
                            source="event_announcement",
                            source_id=self.event.pk,
                            success=True,
                        ).exists()
                    )

    def test_signup_only_fire_rejects_non_org_staff(self) -> None:
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = "signup-channel"
        self.event.discord_announcement = False
        self.event.save()
        self._seed_signup_post()
        outsider = CustomUser.objects.create_user(
            username="signup-outsider", password="test"
        )
        self.client.force_authenticate(user=outsider)
        with patch("events.views.current_app") as app:
            response = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/signup_post/fire/"
            )
        self.assertEqual(response.status_code, 403)
        app.send_task.assert_not_called()
        self.assertTrue(DiscordEventMsgSignup.objects.get(event=self.event).has_posted)
        self.assertTrue(
            DiscordMessageLog.objects.get(
                source="event_announcement", source_id=self.event.pk
            ).success
        )

    def test_signup_post_repost_clears_dedup_and_dispatches(self) -> None:
        """The 409 idempotency guard is intentionally lifted for signup_post.
        We expect dedup state cleared AND celery dispatch."""

        # Seed dedup state as if a prior post had succeeded.
        DiscordEventMsgSignup.objects.create(
            event_id=self.event.pk,
            channel_id="ch_ann",
            has_posted=True,
            message_id="old_msg",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=self.event.pk,
            success=True,
            channel_id="ch_ann",
            embed_data={"title": "seed"},
        )

        with patch("events.views.current_app") as mock_app:
            resp = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/signup_post/fire/"
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        # Dedup cleared on both gates.
        self.assertFalse(
            DiscordEventMsgSignup.objects.filter(
                event_id=self.event.pk, has_posted=True
            ).exists()
        )
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_announcement",
                source_id=self.event.pk,
                success=True,
            ).exists()
        )
        # send_event_announcement dispatched with the event id.
        mock_app.send_task.assert_called_once_with(
            "events.tasks.send_event_announcement",
            args=[self.event.pk],
            kwargs={"generation": 1, "manual": True, "fired_by_user_id": self.admin.pk},
        )


REPOST_ALIASES = ("signup_post", "announcement")


class FireSignupDeliveryFenceTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(name="Fence Org")
        self.event = Event.objects.create(
            organization=self.org,
            name="Synthetic Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            discord_announcement=True,
            discord_announcement_channel_id=PRIMARY,
        )
        self.admin = CustomUser.objects.create_superuser(
            username="fence_admin", password="x"
        )
        self.client.force_authenticate(user=self.admin)

    def fire(self, task: str = "signup_post", **body: Any) -> tuple[Any, MagicMock]:
        with patch("events.views.current_app") as app:
            resp = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/{task}/fire/",
                body,
                format="json",
            )
        return resp, app

    def set_state(self, **fields: Any) -> SignupPostDeliveryState:
        state, _ = SignupPostDeliveryState.objects.get_or_create(event=self.event)
        for name, value in fields.items():
            setattr(state, name, value)
        state.save()
        return state

    def state(self) -> SignupPostDeliveryState:
        return SignupPostDeliveryState.objects.get(event=self.event)

    def test_repost_aliases_reset_generation_and_enqueue_with_generation(
        self,
    ) -> None:
        self.set_state(generation=3, attempts=2)
        for expected, task in enumerate(REPOST_ALIASES, start=4):
            with self.subTest(task=task):
                resp, app = self.fire(task)
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(
                    resp.json(), {"fired": task, "event_id": self.event.pk}
                )
                app.send_task.assert_called_once_with(
                    "events.tasks.send_event_announcement",
                    args=[self.event.pk],
                    kwargs={
                        "generation": expected,
                        "manual": True,
                        "fired_by_user_id": self.admin.pk,
                    },
                )
                self.assertEqual(self.state().generation, expected)
                self.assertEqual(self.state().attempts, 0)

    def test_repost_rejects_nonstaff(self) -> None:
        self.set_state(generation=2, state=SignupDeliveryStatus.EXHAUSTED, attempts=5)
        outsider = CustomUser.objects.create_user(username="fence_outsider")
        self.client.force_authenticate(user=outsider)
        for task in REPOST_ALIASES:
            resp, app = self.fire(task)
            self.assertEqual(resp.status_code, 403)
            app.send_task.assert_not_called()
        self.client.force_authenticate(user=None)
        for task in REPOST_ALIASES:
            resp, app = self.fire(task)
            self.assertEqual(resp.status_code, 403)
            app.send_task.assert_not_called()
        self.assertEqual(self.state().generation, 2)
        self.assertEqual(self.state().state, SignupDeliveryStatus.EXHAUSTED)

    def test_repost_while_active_returns_409_and_keeps_state(self) -> None:
        DiscordEventMsgSignup.objects.create(
            event=self.event, channel_id=PRIMARY, has_posted=True, message_id="9"
        )
        cases: dict[str, Any] = {
            "reserved": lambda: self.set_state(
                state=SignupDeliveryStatus.RESERVED, reserved_at=timezone.now()
            ),
            "pending_lease": lambda: DiscordMessageLog.objects.create(
                source="event_announcement",
                source_id=self.event.pk,
                success=None,
                channel_id=PRIMARY,
                embed_data={},
            ),
        }
        for name, arrange in cases.items():
            for task in REPOST_ALIASES:
                with self.subTest(case=name, task=task):
                    SignupPostDeliveryState.objects.filter(event=self.event).delete()
                    DiscordMessageLog.objects.filter(source_id=self.event.pk).delete()
                    self.set_state(generation=7, attempts=1)
                    arrange()
                    resp, app = self.fire(task)
                    self.assertEqual(resp.status_code, 409, resp.content)
                    self.assertEqual(
                        resp.json(),
                        {
                            "error": "A signup post attempt is already in progress. "
                            "Try again after it finishes."
                        },
                    )
                    app.send_task.assert_not_called()
                    self.assertEqual(self.state().generation, 7)
                    self.assertEqual(self.state().attempts, 1)
                    self.assertTrue(
                        DiscordEventMsgSignup.objects.get(event=self.event).has_posted
                    )

    def test_repost_uncertain_allowed(self) -> None:
        self.set_state(
            generation=1,
            attempts=1,
            state=SignupDeliveryStatus.UNCERTAIN,
            reserved_at=timezone.now(),
        )
        resp, app = self.fire()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(app.send_task.call_args.kwargs["kwargs"]["generation"], 2)
        self.assertEqual(self.state().state, SignupDeliveryStatus.READY)

    def test_repost_resets_exhaustion(self) -> None:
        self.set_state(
            generation=4,
            attempts=5,
            state=SignupDeliveryStatus.EXHAUSTED,
            next_attempt_at=timezone.now() + timedelta(minutes=8),
            last_failure_status=403,
            last_failure_code=50013,
        )
        resp, _ = self.fire("announcement")
        self.assertEqual(resp.status_code, 200, resp.content)
        state = self.state()
        self.assertEqual(
            (state.generation, state.attempts, state.state, state.next_attempt_at),
            (5, 0, SignupDeliveryStatus.READY, None),
        )
        self.assertIsNone(state.last_failure_code)

    def test_repost_enqueue_failure_returns_503_and_generation_claimable(
        self,
    ) -> None:
        self.set_state(generation=2, attempts=5, state=SignupDeliveryStatus.EXHAUSTED)
        with patch("events.views.current_app") as app:
            app.send_task.side_effect = ConnectionError("broker down")
            resp = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/signup_post/fire/"
            )
        self.assertEqual(resp.status_code, 503, resp.content)
        self.assertEqual(
            resp.json(),
            {"error": "Could not queue the signup post. Automatic posting will retry."},
        )
        self.assertNotIn("broker", resp.content.decode())
        decision = begin_signup_attempt(self.event.pk)
        self.assertEqual(decision.outcome, BeginOutcome.RESERVED)
        self.assertEqual(decision.generation, 3)
        self.assertEqual(decision.attempt, 1)

    def test_repost_actor_from_request_ignores_body_actor(self) -> None:
        other = CustomUser.objects.create_user(username="fence_other")
        resp, app = self.fire(
            fired_by_user_id=other.pk, manual=False, generation=99, user_id=other.pk
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        kwargs = app.send_task.call_args.kwargs["kwargs"]
        self.assertEqual(kwargs["fired_by_user_id"], self.admin.pk)
        self.assertTrue(kwargs["manual"])
        self.assertEqual(kwargs["generation"], self.state().generation)
        self.assertNotEqual(kwargs["generation"], 99)


class UncertainFirstAttemptScheduleTest(DiscordTestMixin, EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.post_event = self.make_event(
            name="Synthetic Event",
            discord_post_signups=True,
            discord_post_signups_channel_id=PRIMARY,
            discord_announcement=False,
        )
        self.http: MagicMock = self.enterContext(
            patch("discordbot.utils.requests.request", side_effect=self.request)
        )
        self.enterContext(patch("discordbot.utils._acquire_rate_limit_token"))
        self.enterContext(
            patch("discordbot.utils._time.sleep", side_effect=AssertionError("sleep"))
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.assertTrue(url.startswith(f"{DISCORD_API_BASE}/channels/{PRIMARY}"))
        if method == "GET":
            return response(200, {"id": PRIMARY, "guild_id": GUILD, "type": 0})
        raise requests.Timeout()

    def signup_row(self) -> dict[str, Any]:
        resp = self.client.get(f"/api/events/{self.post_event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        return next(t for t in resp.json() if t["task"] == "signup_post")

    def test_uncertain_first_attempt_schedule_not_fired_and_manual_reset_allowed(
        self,
    ) -> None:
        result = run_signup_post(self.post_event.pk)
        self.assertEqual(result.outcome, SignupRunOutcome.UNCERTAIN)
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_announcement", source_id=self.post_event.pk, success=True
            ).exists()
        )
        self.assertFalse(
            DiscordEventLog.objects.filter(
                discord_event__event=self.post_event,
                action="send_signup_post",
                success=True,
            ).exists()
        )
        row = self.signup_row()
        self.assertEqual(
            row,
            {
                "task": "signup_post",
                "label": "Signup Post",
                "fires_at": None,
                "description": "Creates forum thread or message for signups",
                "check_interval": "On signups open",
                "last_fired_at": None,
                "fired_by": None,
                "can_fire": True,
                "status": "ready",
            },
        )

        url = f"/api/events/{self.post_event.pk}/task-schedule/signup_post/fire/"
        with patch("events.views.current_app") as app:
            self.assertEqual(self.client.post(url).status_code, 409)
        app.send_task.assert_not_called()

        DiscordMessageLog.objects.filter(source_id=self.post_event.pk).update(
            claimed_at=timezone.now() - timedelta(minutes=10)
        )
        sweep = APIRequestFactory().post(
            "/api/internal/discord/sweep-stale-leases/",
            {"pending_threshold_minutes": 5},
            format="json",
        )
        force_authenticate(sweep, user=InternalServiceUser())
        self.assertEqual(sweep_stale_discord_leases(sweep).data["pending_swept"], 1)
        self.assertEqual(self.signup_row(), row)

        with patch("events.views.current_app") as app:
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        app.send_task.assert_called_once_with(
            "events.tasks.send_event_announcement",
            args=[self.post_event.pk],
            kwargs={"generation": 1, "manual": True, "fired_by_user_id": self.admin.pk},
        )
        self.assertEqual(
            len([c for c in self.http.call_args_list if c.args[0] == "POST"]), 1
        )


class ScheduledEventPastStartTest(TestCase):
    """Once an event's start has passed, Discord rejects a scheduled event for
    it, so the panel must not offer it and the fire endpoint must refuse it.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(
            name="Past Start Org", discord_server_id="111"
        )
        self.admin = CustomUser.objects.create_superuser(
            username="past_start_admin", password="x"
        )
        self.client.force_authenticate(user=self.admin)

    def _event(self, starts_in: timedelta) -> Event:
        return Event.objects.create(
            organization=self.org,
            name="Past Start Event",
            state="signups_open",
            scheduled_at=timezone.now() + starts_in,
            discord_create_event=True,
        )

    def _scheduled_event_row(self, event: Event) -> dict[str, Any]:
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        return next(t for t in resp.json() if t["task"] == "scheduled_event")

    def test_past_start_is_disabled_and_not_fireable(self) -> None:
        row = self._scheduled_event_row(self._event(-timedelta(hours=2)))
        self.assertEqual(row["status"], "disabled")
        self.assertFalse(row["can_fire"])
        self.assertIn("Start time has passed", row["description"])

    def test_fired_past_start_stays_fired(self) -> None:
        event = self._event(-timedelta(hours=2))
        discord_event, _ = DiscordEvent.objects.get_or_create(
            event=event, defaults={"guild_id": "111"}
        )
        DiscordEventLog.objects.create(
            discord_event=discord_event,
            action="create_scheduled_event",
            success=True,
        )
        row = self._scheduled_event_row(event)
        self.assertEqual(row["status"], "fired")
        self.assertEqual(row["description"], "Creates a Discord guild scheduled event")

    def test_future_start_is_ready(self) -> None:
        row = self._scheduled_event_row(self._event(timedelta(hours=2)))
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["can_fire"])

    def test_fire_rejects_past_start(self) -> None:
        event = self._event(-timedelta(hours=2))
        with patch("events.views.current_app") as mock_app:
            resp = self.client.post(
                f"/api/events/{event.pk}/task-schedule/scheduled_event/fire/"
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["error"], "Event start time has passed")
        mock_app.send_task.assert_not_called()


class FireHeroDraftDmTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(name="HeroDraft DM Org")
        self.tournament = Tournament.objects.create(
            name="HeroDraft DM Tournament", date_played=timezone.now()
        )
        captain1 = CustomUser.objects.create_user(username="hd_cap1", password="x")
        captain2 = CustomUser.objects.create_user(username="hd_cap2", password="x")
        self.radiant = Team.objects.create(
            name="Radiant Team", tournament=self.tournament, captain=captain1
        )
        self.dire = Team.objects.create(
            name="Dire Team", tournament=self.tournament, captain=captain2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.radiant,
            dire_team=self.dire,
        )
        self.herodraft = HeroDraft.objects.create(game=self.game)
        self.event = Event.objects.create(
            organization=self.org,
            name="HeroDraft DM Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(hours=24),
            tournament=self.tournament,
        )
        admin = CustomUser.objects.create_superuser(username="hd_admin", password="x")
        self.client.force_authenticate(user=admin)

    def test_resend_passes_game_id_to_task(self) -> None:
        with patch("events.views.current_app") as mock_app:
            resp = self.client.post(
                f"/api/events/{self.event.pk}/task-schedule/herodraft_dm/fire/"
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        mock_app.send_task.assert_called_once()
        call = mock_app.send_task.call_args
        self.assertEqual(
            call.args[0], "events.tournament_tasks.send_tournament_herodraft_links"
        )
        args = list(call.kwargs.get("args", []))
        kwargs = dict(call.kwargs.get("kwargs") or {})
        params = dict(
            zip(
                [
                    "tournament_id",
                    "herodraft_id",
                    "game_id",
                    "radiant_name",
                    "dire_name",
                ],
                args,
            )
        )
        params.update(kwargs)
        self.assertEqual(params["tournament_id"], self.tournament.pk)
        self.assertEqual(params["herodraft_id"], self.herodraft.pk)
        self.assertEqual(params["game_id"], self.game.pk)
        self.assertEqual(params["radiant_name"], "Radiant Team")
        self.assertEqual(params["dire_name"], "Dire Team")
