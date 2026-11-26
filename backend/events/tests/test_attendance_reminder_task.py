"""Test the extracted send_attendance_reminder shared task."""

from unittest.mock import MagicMock, patch

from discordbot.models import DiscordMessageLog
from events.tasks import send_attendance_reminder
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response

OWN_CHANNEL = "333333333333333333"
ANNOUNCEMENT_CHANNEL = "1482767177063858216"


class SendAttendanceReminderTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_sends_attendance_embed_to_announcement_channel(self, mock_req):
        mock_req.return_value = _ok_response({"id": "att_msg_1"})
        self.event.discord_confirm_attendance = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.state = "signups_open"
        self.event.save()

        send_attendance_reminder(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, "1482767177063858216")
        self.assertEqual(log.discord_message_id, "att_msg_1")

    @patch("discordbot.utils._rate_limited_request")
    def test_sends_to_own_channel_when_set(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "att_msg_2"})
        self.event.discord_confirm_attendance = True
        self.event.discord_confirm_attendance_channel_id = OWN_CHANNEL
        self.event.discord_announcement_channel_id = ANNOUNCEMENT_CHANNEL
        self.event.save()

        send_attendance_reminder(self.event.pk)

        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, OWN_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_blank_own_channel_uses_announcement(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "att_msg_3"})
        self.event.discord_confirm_attendance = True
        self.event.discord_confirm_attendance_channel_id = ""
        self.event.discord_announcement_channel_id = ANNOUNCEMENT_CHANNEL
        self.event.save()

        send_attendance_reminder(self.event.pk)

        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, ANNOUNCEMENT_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_own_channel_without_announcement_channel_sends(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.return_value = _ok_response({"id": "att_msg_4"})
        self.event.discord_confirm_attendance = True
        self.event.discord_confirm_attendance_channel_id = OWN_CHANNEL
        self.event.discord_announcement_channel_id = ""
        self.event.save()

        send_attendance_reminder(self.event.pk)

        mock_req.assert_called_once()
        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, OWN_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_skips_when_no_announcement_channel(self, mock_req):
        # CharField with blank="" — empty string represents 'unset' here
        self.event.discord_confirm_attendance = True
        self.event.discord_announcement_channel_id = ""
        self.event.save()

        result = send_attendance_reminder(self.event.pk)
        mock_req.assert_not_called()
        self.assertIn("no channel", result.lower())

    def test_acks_late_decorator(self):
        self.assertTrue(send_attendance_reminder.acks_late)
        self.assertTrue(send_attendance_reminder.reject_on_worker_lost)
