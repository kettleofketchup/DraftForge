from unittest.mock import MagicMock, patch

from django.test import TestCase

from discordbot.models import DiscordMessageLog


class WaitForDiscordLogTest(TestCase):
    def test_returns_log_when_exists(self):
        from discordbot.test_utils import wait_for_discord_log

        DiscordMessageLog.objects.create(
            channel_id="123",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=42,
            success=True,
        )

        log = wait_for_discord_log("event_announcement", 42, timeout=1)
        self.assertIsNotNone(log)
        self.assertTrue(log.success)

    def test_returns_none_on_timeout(self):
        from discordbot.test_utils import wait_for_discord_log

        log = wait_for_discord_log("nonexistent", 999, timeout=1)
        self.assertIsNone(log)


class FetchChannelMessagesTest(TestCase):
    @patch("discordbot.test_utils.requests.get")
    def test_returns_messages_list(self, mock_get):
        from discordbot.test_utils import fetch_channel_messages

        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value=[
                    {"id": "111", "embeds": [{"title": "Test"}]},
                    {"id": "222", "embeds": []},
                ]
            ),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        messages = fetch_channel_messages("123456789")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["id"], "111")


class AssertDiscordMessageDeliveredTest(TestCase):
    @patch("discordbot.test_utils.fetch_channel_messages")
    def test_finds_matching_message(self, mock_fetch):
        from discordbot.test_utils import assert_discord_message_delivered

        log = DiscordMessageLog.objects.create(
            channel_id="123",
            embed_data={"title": "Weekly Inhouse"},
            source="event_announcement",
            source_id=1,
            discord_message_id="444555666",
            success=True,
        )

        mock_fetch.return_value = [
            {"id": "444555666", "embeds": [{"title": "Weekly Inhouse"}]},
        ]

        result = assert_discord_message_delivered(log)
        self.assertTrue(result)

    @patch("discordbot.test_utils.fetch_channel_messages")
    def test_returns_false_when_not_found(self, mock_fetch):
        from discordbot.test_utils import assert_discord_message_delivered

        log = DiscordMessageLog.objects.create(
            channel_id="123",
            embed_data={"title": "Missing"},
            source="event_announcement",
            source_id=1,
            discord_message_id="999",
            success=True,
        )

        mock_fetch.return_value = []

        result = assert_discord_message_delivered(log)
        self.assertFalse(result)
