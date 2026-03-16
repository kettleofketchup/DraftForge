from unittest.mock import MagicMock, patch

from django.test import TestCase
from requests.exceptions import HTTPError


class SyncSendEmbedLoggingTest(TestCase):
    @patch("discordbot.utils.requests.post")
    def test_send_embed_creates_log_on_success(self, mock_post):
        """sync_send_embed creates a DiscordMessageLog entry on success."""
        from discordbot.models import DiscordMessageLog
        from discordbot.utils import sync_send_embed

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "111222333"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        sync_send_embed(
            channel_id="123456789",
            title="Test",
            description="Desc",
            color=0x00FF00,
            source="event_announcement",
            source_id=42,
        )

        log = DiscordMessageLog.objects.get(source="event_announcement", source_id=42)
        self.assertTrue(log.success)
        self.assertEqual(log.discord_message_id, "111222333")
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.channel_id, "123456789")

    @patch("discordbot.utils.requests.post")
    def test_send_embed_creates_log_on_failure(self, mock_post):
        """sync_send_embed creates a DiscordMessageLog entry on API failure."""
        from discordbot.models import DiscordMessageLog
        from discordbot.utils import sync_send_embed

        mock_response = MagicMock(status_code=403)
        mock_response.json.return_value = {"message": "Missing Access"}
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        sync_send_embed(
            channel_id="123456789",
            title="Test",
            description="Desc",
            color=0xFF0000,
            source="signup_update",
            source_id=7,
        )

        log = DiscordMessageLog.objects.get(source="signup_update", source_id=7)
        self.assertFalse(log.success)
        self.assertEqual(log.status_code, 403)

    @patch("discordbot.utils.requests.post")
    def test_send_embed_without_source_uses_unknown(self, mock_post):
        """sync_send_embed defaults source to 'unknown' when not provided."""
        from discordbot.models import DiscordMessageLog
        from discordbot.utils import sync_send_embed

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "444555666"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        sync_send_embed(
            channel_id="123456789",
            title="Test",
            description="Desc",
            color=0x00FF00,
        )

        log = DiscordMessageLog.objects.last()
        self.assertEqual(log.source, "unknown")
