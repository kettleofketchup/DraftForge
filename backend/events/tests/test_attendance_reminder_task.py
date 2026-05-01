"""Test the extracted send_attendance_reminder shared task."""

from unittest.mock import patch

from discordbot.models import DiscordMessageLog
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response


class SendAttendanceReminderTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_sends_attendance_embed_to_announcement_channel(self, mock_req):
        mock_req.return_value = _ok_response({"id": "att_msg_1"})
        self.event.discord_confirm_attendance = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.state = "signups_open"
        self.event.save()

        from events.tasks import send_attendance_reminder

        send_attendance_reminder(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, "1482767177063858216")
        self.assertEqual(log.discord_message_id, "att_msg_1")

    @patch("discordbot.utils._rate_limited_request")
    def test_skips_when_no_announcement_channel(self, mock_req):
        # CharField with blank="" — empty string represents 'unset' here
        self.event.discord_confirm_attendance = True
        self.event.discord_announcement_channel_id = ""
        self.event.save()

        from events.tasks import send_attendance_reminder

        result = send_attendance_reminder(self.event.pk)
        mock_req.assert_not_called()
        self.assertIn("no channel", result.lower())

    def test_acks_late_decorator(self):
        from events.tasks import send_attendance_reminder

        self.assertTrue(send_attendance_reminder.acks_late)
        self.assertTrue(send_attendance_reminder.reject_on_worker_lost)
