from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Organization


class TaskScheduleEndpointTest(TestCase):
    def setUp(self):
        from events.models import Event

        self.client = APIClient()
        self.org = Organization.objects.create(name="Schedule Test Org")
        self.event = Event.objects.create(
            organization=self.org,
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
            discord_subscriber_dm=True,
            discord_subscriber_dm_hours=12,
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
        self.assertIn("signup_reminder", task_names)
        self.assertIn("confirm_attendance", task_names)
        self.assertIn("profile_reminder", task_names)
        self.assertIn("subscriber_dm", task_names)
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
            discord_subscriber_dm=False,
            discord_create_event=False,
        )
        resp = self.client.get(f"/api/events/{event.pk}/task-schedule/")
        tasks = resp.json()
        for task in tasks:
            if task["task"] in (
                "signup_reminder",
                "confirm_attendance",
                "profile_reminder",
                "subscriber_dm",
                "scheduled_event",
            ):
                self.assertEqual(
                    task["status"], "disabled", f"{task['task']} should be disabled"
                )

    def test_fired_tasks_detected(self):
        from discordbot.models import DiscordMessageLog

        DiscordMessageLog.objects.create(
            channel_id="123456",
            embed_data={"test": True},
            source="signup_reminder",
            source_id=self.event.pk,
            success=True,
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
