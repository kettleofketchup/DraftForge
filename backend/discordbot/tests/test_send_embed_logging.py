from unittest.mock import MagicMock, patch

from django.test import TestCase
from requests.exceptions import HTTPError


class SyncEditMessageTest(TestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_edit_message_sends_patch(self, mock_request):
        from discordbot.utils import sync_edit_message

        mock_request.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "111222333"}),
        )
        mock_request.return_value.raise_for_status = MagicMock()

        result = sync_edit_message(
            channel_id="123456789",
            message_id="111222333",
            embed={"title": "Updated", "description": "New content", "color": 0x00FF00},
        )

        mock_request.assert_called_once()
        self.assertEqual(mock_request.call_args[0][0], "PATCH")
        self.assertIsNotNone(result)

    @patch("discordbot.utils._rate_limited_request")
    def test_edit_message_with_components(self, mock_request):
        from discordbot.utils import sync_edit_message

        mock_request.return_value = MagicMock(status_code=200)
        mock_request.return_value.json.return_value = {"id": "111222333"}
        mock_request.return_value.raise_for_status = MagicMock()

        components = [
            {
                "type": 1,
                "components": [{"type": 2, "label": "Click", "custom_id": "test"}],
            }
        ]
        sync_edit_message(
            channel_id="123456789",
            message_id="111222333",
            embed={"title": "Test"},
            components=components,
        )

        call_args = mock_request.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        self.assertIn("components", payload)


class SyncSendEmbedLoggingTest(TestCase):
    """sync_send_embed logs via the internal HTTP API (app.internal_client.create_message_log),
    not direct DB writes — Django/Daphne is the sole DB writer to avoid SQLite lock contention.
    These tests verify the logging call is made with the right payload."""

    @patch("app.internal_client.create_message_log")
    @patch("discordbot.utils._rate_limited_request")
    def test_send_embed_logs_via_internal_api_on_success(
        self, mock_request, mock_create_log
    ):
        from discordbot.utils import sync_send_embed

        mock_request.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "111222333"}),
        )
        mock_request.return_value.raise_for_status = MagicMock()
        mock_create_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        sync_send_embed(
            channel_id="123456789",
            title="Test",
            description="Desc",
            color=0x00FF00,
            source="event_announcement",
            source_id=42,
        )

        mock_create_log.assert_called_once()
        kwargs = mock_create_log.call_args.kwargs
        self.assertEqual(kwargs["channel_id"], "123456789")
        self.assertEqual(kwargs["source"], "event_announcement")
        self.assertEqual(kwargs["source_id"], 42)
        self.assertEqual(kwargs["status_code"], 200)
        self.assertEqual(kwargs["discord_message_id"], "111222333")
        self.assertTrue(kwargs["success"])

    @patch("app.internal_client.create_message_log")
    @patch("discordbot.utils._rate_limited_request")
    def test_send_embed_logs_via_internal_api_on_failure(
        self, mock_request, mock_create_log
    ):
        from discordbot.utils import sync_send_embed

        mock_response = MagicMock(status_code=403)
        mock_response.json.return_value = {"message": "Missing Access"}
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_request.return_value = mock_response
        mock_create_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        sync_send_embed(
            channel_id="123456789",
            title="Test",
            description="Desc",
            color=0xFF0000,
            source="signup_update",
            source_id=7,
        )

        mock_create_log.assert_called_once()
        kwargs = mock_create_log.call_args.kwargs
        self.assertEqual(kwargs["source"], "signup_update")
        self.assertEqual(kwargs["source_id"], 7)
        self.assertEqual(kwargs["status_code"], 403)
        self.assertFalse(kwargs["success"])

    @patch("app.internal_client.create_message_log")
    @patch("discordbot.utils._rate_limited_request")
    def test_send_embed_without_source_uses_unknown(
        self, mock_request, mock_create_log
    ):
        from discordbot.utils import sync_send_embed

        mock_request.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "444555666"}),
        )
        mock_request.return_value.raise_for_status = MagicMock()
        mock_create_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        sync_send_embed(
            channel_id="123456789",
            title="Test",
            description="Desc",
            color=0x00FF00,
        )

        mock_create_log.assert_called_once()
        self.assertEqual(mock_create_log.call_args.kwargs["source"], "unknown")
