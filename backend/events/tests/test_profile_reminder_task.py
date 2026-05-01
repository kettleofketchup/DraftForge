"""Test the extracted send_profile_reminder shared task."""

from unittest.mock import patch

from discordbot.models import DiscordMessageLog
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response


class SendProfileReminderTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_sends_profile_embed_to_announcement_channel(self, mock_req):
        mock_req.return_value = _ok_response({"id": "prof_msg_1"})
        self.event.discord_profile_reminder = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.state = "signups_open"
        self.event.save()

        from events.tasks import send_profile_reminder

        send_profile_reminder(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="profile_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, "1482767177063858216")
        self.assertEqual(log.discord_message_id, "prof_msg_1")

    @patch("discordbot.utils._rate_limited_request")
    def test_skips_when_no_announcement_channel(self, mock_req):
        self.event.discord_profile_reminder = True
        self.event.discord_announcement_channel_id = ""
        self.event.save()

        from events.tasks import send_profile_reminder

        result = send_profile_reminder(self.event.pk)
        mock_req.assert_not_called()
        self.assertIn("no channel", result.lower())

    def test_acks_late_decorator(self):
        from events.tasks import send_profile_reminder

        self.assertTrue(send_profile_reminder.acks_late)
        self.assertTrue(send_profile_reminder.reject_on_worker_lost)
