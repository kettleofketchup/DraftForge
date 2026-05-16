from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Organization


class TaskScheduleEndpointTest(TestCase):
    def setUp(self):
        from events.models import Event, EventRepeater

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

    def test_returns_task_list(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.json()
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)

    def test_includes_all_enabled_tasks(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        task_names = [t["task"] for t in tasks]
        self.assertIn("announcement", task_names)
        # signup_reminder absorbed the former subscriber_dm task — it now drives
        # subscriber DMs and uses has_dms for fired detection.
        self.assertIn("signup_reminder", task_names)
        self.assertIn("confirm_attendance", task_names)
        self.assertIn("profile_reminder", task_names)
        self.assertIn("scheduled_event", task_names)

    def test_includes_fires_at(self):
        resp = self.client.get(f"/api/events/{self.event.pk}/task-schedule/")
        tasks = resp.json()
        reminder = next(t for t in tasks if t["task"] == "signup_reminder")
        self.assertIn("fires_at", reminder)
        self.assertIsNotNone(reminder["fires_at"])

    def test_disabled_tasks_show_disabled(self):
        from events.models import Event

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

    def test_fired_tasks_detected(self):
        # signup_reminder fired status is driven by DiscordEventDM rows
        # (subscriber DMs sent), not DiscordMessageLog.
        from discordbot.models import DiscordEvent, DiscordEventDM, DMType
        from org.models import OrgUser

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

    def test_announcement_misconfigured(self):
        """Announcement enabled but no channel ID → misconfigured."""
        from events.models import Event

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

    def test_requires_authentication(self):
        client = APIClient()  # not authenticated
        resp = client.get(f"/api/events/{self.event.pk}/task-schedule/")
        self.assertEqual(resp.status_code, 403)

    def test_404_for_nonexistent_event(self):
        resp = self.client.get("/api/events/99999/task-schedule/")
        self.assertEqual(resp.status_code, 404)

    def test_signup_post_can_fire_when_already_fired(self):
        """signup_post (and announcement) must stay re-fireable so admin can
        repost when the Discord post was deleted or needs a refresh. Other
        tasks (one-shot DMs, reminders) stay non-fireable once fired.
        """
        from discordbot.models import DiscordEvent, DiscordEventLog

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

    def setUp(self):
        from events.models import Event

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
        # has_org_staff_access goes through has_org_admin_access which accepts
        # is_superuser; plain is_staff doesn't qualify as org staff.
        self.admin = CustomUser.objects.create_superuser(
            username="repost_admin", password="x"
        )
        self.client.force_authenticate(user=self.admin)

    def test_signup_post_repost_clears_dedup_and_dispatches(self):
        """The 409 idempotency guard is intentionally lifted for signup_post.
        We expect dedup state cleared AND celery dispatch."""
        from unittest.mock import patch

        from discordbot.models import DiscordEventMsgSignup, DiscordMessageLog

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

        # Patch the celery current_app the view imports. The view does
        # `from celery import current_app` inside the function so the import
        # resolves at call time against the module-level proxy we replace.
        with patch("celery.current_app") as mock_app:
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
            "events.tasks.send_event_announcement", args=[self.event.pk]
        )
