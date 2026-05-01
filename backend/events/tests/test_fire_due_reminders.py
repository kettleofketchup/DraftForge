"""Test the registry-driven fire path."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from discordbot.models import DiscordMessageLog
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class FireDueRemindersTest(_DiscordTaskTestCase):
    """Tests use _DiscordTaskTestCase so internal_client calls go through
    the ORM-mock map (no HTTP)."""

    @patch("events.scheduling.fire.current_app.send_task")
    def test_fires_announcement_when_threshold_passed(self, mock_send):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()

        # Assert the announcement task was dispatched by name
        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(len(announcement_calls), 1)
        self.assertEqual(announcement_calls[0].kwargs["args"], [self.event.pk])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_does_not_fire_before_threshold(self, mock_send):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(days=7)  # threshold +6 days
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()

        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_skips_if_already_fired(self, mock_send):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=self.event.pk,
            success=True,
            channel_id="ch_1",
            embed_data={"title": "prior"},
        )

        fire_due_reminders()

        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_skips_if_disabled(self, mock_send):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = False
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()

        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])

    @patch("events.scheduling.fire.current_app.send_task")
    def test_skips_if_hours_zero_or_unset(self, mock_send):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 0
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()

        announcement_calls = [
            c for c in mock_send.call_args_list
            if c.args[0] == "events.tasks.send_event_announcement"
        ]
        self.assertEqual(announcement_calls, [])
