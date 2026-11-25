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


class RefreshAvatarsCheckOnlyTest(TestCase):
    def setUp(self) -> None:
        CustomUser.objects.create(
            username="static_user", discordId="1111", avatar="static_hash"
        )
        CustomUser.objects.create(
            username="animated_user", discordId="2222", avatar="a_animated_hash"
        )

    @patch("app.models.requests.get")
    @patch("app.models.requests.head")
    def test_check_only_uses_extension_and_counts_valid(
        self, mock_head: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_head.return_value = _response(200)
        out = StringIO()

        call_command("refresh_avatars", "--check-only", stdout=out)

        checked = {c.args[0] for c in mock_head.call_args_list}
        self.assertEqual(
            checked,
            {
                "https://cdn.discordapp.com/avatars/1111/static_hash.png",
                "https://cdn.discordapp.com/avatars/2222/a_animated_hash.gif",
            },
        )
        mock_get.assert_not_called()
        self.assertIn("Found 0 invalid avatars out of 2 users", out.getvalue())


class DiscordAvatarCdnUrlTest(TestCase):
    def test_static_hash_uses_png(self) -> None:
        user = CustomUser(username="u1", discordId="1111", avatar="abc")
        self.assertEqual(
            user.discord_avatar_cdn_url,
            "https://cdn.discordapp.com/avatars/1111/abc.png",
        )

    def test_animated_hash_uses_gif(self) -> None:
        user = CustomUser(username="u2", discordId="2222", avatar="a_abc")
        self.assertEqual(
            user.discord_avatar_cdn_url,
            "https://cdn.discordapp.com/avatars/2222/a_abc.gif",
        )

    def test_none_without_hash(self) -> None:
        user = CustomUser(username="u3", discordId="3333")
        self.assertIsNone(user.discord_avatar_cdn_url)
