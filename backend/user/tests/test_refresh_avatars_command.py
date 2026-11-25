"""Tests for the `refresh_avatars` management command."""

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from app.models import CustomUser


def _response(status_code: int, payload: dict[str, str] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    return resp


@override_settings(DISCORD_BOT_TOKEN="test-bot-token")
class RefreshAvatarsCommandTest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(
            username="avatar_user", discordId="4242", avatar="old_hash"
        )

    @patch("app.models.requests.get")
    @patch("app.models.requests.head")
    def test_without_force_skips_valid_avatar(
        self, mock_head: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_head.return_value = _response(200)
        mock_get.return_value = _response(200, {"avatar": "new_hash"})

        call_command("refresh_avatars", stdout=StringIO())

        mock_get.assert_not_called()
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, "old_hash")

    @patch("app.models.requests.get")
    @patch("app.models.requests.head")
    def test_force_refetches_valid_avatar(
        self, mock_head: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_head.return_value = _response(200)
        mock_get.return_value = _response(200, {"avatar": "new_hash"})
        out = StringIO()

        call_command("refresh_avatars", "--force", stdout=out)

        mock_get.assert_called_once()
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, "new_hash")
        self.assertIn("Updated 1 avatars out of 1 users", out.getvalue())
