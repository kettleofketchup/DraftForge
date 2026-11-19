"""Test the registry-driven fire path."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from discordbot.models import DiscordMessageLog
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class FireDueRemindersTest(_DiscordTaskTestCase):
    """Tests use _DiscordTaskTestCase so internal_client calls go through
    the ORM-mock map (no HTTP).

    The fire path looks up tasks via current_app.tasks.get(name) and calls
    .delay() — patch the specific task's delay attribute to assert dispatch.
    """

    @patch("events.tasks.send_event_announcement.delay")
    def test_fires_announcement_when_threshold_passed(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_called_once_with(self.event.pk)

    @patch("events.tasks.send_event_announcement.delay")
    def test_does_not_fire_before_threshold(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(
            days=7
        )  # threshold +6 days
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_not_called()

    @patch("events.tasks.send_event_announcement.delay")
    def test_skips_if_already_fired(self, mock_delay):
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
        mock_delay.assert_not_called()

    @patch("events.tasks.send_event_announcement.delay")
    def test_skips_if_disabled(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = False
        self.event.discord_announcement_hours = 24
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_not_called()

    @patch("events.tasks.send_event_announcement.delay")
    def test_skips_if_hours_zero_or_unset(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "ch_1"
        self.event.discord_announcement_hours = 0
        self.event.scheduled_at = timezone.now() + timedelta(hours=12)
        self.event.state = "upcoming"
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_not_called()

    @patch("events.tasks.send_start_mention.delay")
    def test_fires_minute_reminder_once_threshold_passed(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_start_mention = True
        self.event.discord_start_mention_minutes = 15
        self.event.scheduled_at = timezone.now() + timedelta(minutes=10)
        self.event.state = "roll_call"
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_called_once_with(self.event.pk)

    @patch("events.tasks.send_start_mention.delay")
    def test_minute_reminder_waits_for_threshold(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_start_mention = True
        self.event.discord_start_mention_minutes = 15
        # 20 minutes out: an hours-based reading of 15 would already fire.
        self.event.scheduled_at = timezone.now() + timedelta(minutes=20)
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_not_called()

    @patch("events.tasks.send_start_mention.delay")
    def test_minute_reminder_skips_disabled(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_start_mention = False
        self.event.discord_start_mention_minutes = 15
        self.event.scheduled_at = timezone.now() + timedelta(minutes=5)
        self.event.save()

        fire_due_reminders()
        mock_delay.assert_not_called()

    @patch("events.tasks.send_attendance_reminder.delay")
    def test_hour_reminder_unchanged_beside_minute_reminder(self, mock_delay):
        from events.scheduling.fire import fire_due_reminders

        self.event.discord_confirm_attendance = True
        self.event.discord_confirm_attendance_hours = 2
        self.event.discord_start_mention = True
        self.event.discord_start_mention_minutes = 15
        self.event.scheduled_at = timezone.now() + timedelta(minutes=90)
        self.event.save()

        with patch("events.tasks.send_start_mention.delay") as mention_delay:
            fire_due_reminders()
        mock_delay.assert_called_once_with(self.event.pk)
        mention_delay.assert_not_called()
