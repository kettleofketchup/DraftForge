from unittest.mock import MagicMock, patch

from django.test import TestCase

from discordbot.models import DiscordMessageLog
from events.models import EventState
from events.tests.base import EventTestCase


class SendEventAnnouncementTaskTest(EventTestCase):
    @patch("discordbot.utils.requests.post")
    def test_announcement_creates_log(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "111222333"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=self.event.pk
        )
        self.assertTrue(log.success)
        self.assertEqual(log.channel_id, "1482767177063858216")

    @patch("discordbot.utils.requests.post")
    def test_announcement_skipped_when_disabled(self, mock_post):
        self.event.discord_announcement = False
        self.event.save()
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)
        self.assertEqual(
            DiscordMessageLog.objects.filter(source="event_announcement").count(), 0
        )
        mock_post.assert_not_called()


class SendSignupUpdateTaskTest(EventTestCase):
    @patch("discordbot.utils.requests.post")
    def test_signup_update_creates_log(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "444555666"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = "1482767709279096893"
        self.event.save()
        from events.tasks import send_signup_update

        send_signup_update(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="signup_update", source_id=self.event.pk
        )
        self.assertTrue(log.success)

    @patch("discordbot.utils.requests.post")
    def test_signup_update_skipped_when_disabled(self, mock_post):
        self.event.discord_post_signups = False
        self.event.save()
        from events.tasks import send_signup_update

        send_signup_update(self.event.pk)
        self.assertEqual(
            DiscordMessageLog.objects.filter(source="signup_update").count(), 0
        )


class CheckEventRemindersTaskTest(EventTestCase):
    @patch("discordbot.utils.requests.post")
    def test_signup_reminder_sent_when_due(self, mock_post):
        from datetime import timedelta

        from django.utils import timezone

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "rem111"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.scheduled_at = timezone.now() + timedelta(hours=23)
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.discord_signup_reminder = True
        self.event.discord_signup_reminder_hours = 24
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import check_event_reminders

        check_event_reminders()
        self.assertTrue(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).exists()
        )

    @patch("discordbot.utils.requests.post")
    def test_signup_reminder_not_sent_twice(self, mock_post):
        from datetime import timedelta

        from django.utils import timezone

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "rem222"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.scheduled_at = timezone.now() + timedelta(hours=23)
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.discord_signup_reminder = True
        self.event.discord_signup_reminder_hours = 24
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import check_event_reminders

        check_event_reminders()
        check_event_reminders()  # Run again — should NOT send duplicate
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).count(),
            1,
        )
