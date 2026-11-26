"""Test the extracted send_attendance_reminder shared task."""

from unittest.mock import MagicMock, patch

from discordbot.models import DiscordMessageLog
from events.tasks import send_attendance_reminder
from events.tests.test_discord_tasks import _configured_response, _DiscordTaskTestCase

OWN_CHANNEL = "100000000000000001"
ANNOUNCEMENT_CHANNEL = "100000000000000003"


class SendAttendanceReminderTaskTest(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = "200000000000000001"
        self.org.save()

    @patch("discordbot.utils._rate_limited_request")
    def test_sends_attendance_embed_to_announcement_channel(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = _configured_response
        self.event.discord_confirm_attendance = True
        self.event.discord_announcement_channel_id = ANNOUNCEMENT_CHANNEL
        self.event.state = "signups_open"
        self.event.save()

        send_attendance_reminder(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, ANNOUNCEMENT_CHANNEL)
        self.assertEqual(log.discord_message_id, "100000000000000002")

    @patch("discordbot.utils._rate_limited_request")
    def test_sends_to_own_channel_when_set(self, mock_req: MagicMock) -> None:
        mock_req.side_effect = _configured_response
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
        mock_req.side_effect = _configured_response
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
        mock_req.side_effect = _configured_response
        self.event.discord_confirm_attendance = True
        self.event.discord_confirm_attendance_channel_id = OWN_CHANNEL
        self.event.discord_announcement_channel_id = ""
        self.event.save()

        send_attendance_reminder(self.event.pk)

        self.assertEqual(
            [call.args[0] for call in mock_req.call_args_list], ["GET", "POST"]
        )
        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, OWN_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_skips_when_no_announcement_channel(self, mock_req: MagicMock) -> None:
        self.event.discord_confirm_attendance = True
        self.event.discord_announcement_channel_id = ""
        self.event.save()

        result = send_attendance_reminder(self.event.pk)
        mock_req.assert_not_called()
        self.assertIn("no channel", result.lower())

    def test_acks_late_decorator(self) -> None:
        self.assertTrue(send_attendance_reminder.acks_late)
        self.assertTrue(send_attendance_reminder.reject_on_worker_lost)
