"""Discord REST calls must be bounded and must not run without credentials.

A request with no timeout blocks forever when egress is filtered (the TCP
handshake never completes), and a request sent with an empty bot token can
only fail. These tests pin both rules for the helpers that seeding and the
admin views reach.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from app.models import CustomUser
from discordbot.services.discord_members import (
    DISCORD_HTTP_TIMEOUT_S,
    get_discord_members_data,
)


def _ok(payload):
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class GetDiscordMembersDataTest(TestCase):
    @override_settings(DISCORD_BOT_TOKEN=None)
    @patch("discordbot.services.discord_members.requests.get")
    def test_skips_request_when_bot_token_missing(self, mock_get):
        self.assertEqual(get_discord_members_data(guild_id=1), [])
        mock_get.assert_not_called()

    @override_settings(DISCORD_BOT_TOKEN="")
    @patch("discordbot.services.discord_members.requests.get")
    def test_skips_request_when_bot_token_empty(self, mock_get):
        self.assertEqual(get_discord_members_data(guild_id=2), [])
        mock_get.assert_not_called()

    @override_settings(DISCORD_BOT_TOKEN="token")
    @patch("discordbot.services.discord_members.requests.get")
    def test_passes_timeout_when_token_configured(self, mock_get):
        member = {"user": {"id": "1", "avatar": "a"}}
        mock_get.return_value = _ok([member])

        self.assertEqual(get_discord_members_data(guild_id=3), [member])
        self.assertEqual(mock_get.call_args.kwargs["timeout"], DISCORD_HTTP_TIMEOUT_S)
        self.assertEqual(
            mock_get.call_args.kwargs["headers"], {"Authorization": "Bot token"}
        )


class RateLimitedRequestTimeoutTest(TestCase):
    @patch("discordbot.utils._acquire_rate_limit_token", return_value=True)
    @patch("discordbot.utils.requests.request")
    def test_applies_default_timeout(self, mock_request, _acquire):
        from discordbot.utils import _rate_limited_request

        mock_request.return_value = MagicMock(status_code=200)
        _rate_limited_request("POST", "https://example.invalid", json={})
        self.assertEqual(
            mock_request.call_args.kwargs["timeout"], DISCORD_HTTP_TIMEOUT_S
        )

    @patch("discordbot.utils._acquire_rate_limit_token", return_value=True)
    @patch("discordbot.utils.requests.request")
    def test_keeps_explicit_timeout(self, mock_request, _acquire):
        from discordbot.utils import _rate_limited_request

        mock_request.return_value = MagicMock(status_code=200)
        _rate_limited_request("GET", "https://example.invalid", timeout=3)
        self.assertEqual(mock_request.call_args.kwargs["timeout"], 3)


class VoiceChannelActivityTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            username="voice-staff", password="x", is_staff=True
        )

    def _call(self):
        from discordbot.services.users import get_discord_voice_channel_activity

        request = APIRequestFactory().get("/api/discord/voice/")
        force_authenticate(request, user=self.staff)
        return get_discord_voice_channel_activity(request)

    # users.py reads `backend.settings` directly, so override_settings does
    # not reach it; patch the module attribute instead.
    @patch("discordbot.services.users.settings.DISCORD_BOT_TOKEN", None)
    @patch("discordbot.services.users.requests.get")
    def test_skips_request_when_bot_token_missing(self, mock_get):
        response = self._call()
        mock_get.assert_not_called()
        self.assertEqual(response.status_code, 503)

    @patch("discordbot.services.users.settings.DISCORD_BOT_TOKEN", "token")
    @patch("discordbot.services.users.requests.get")
    def test_passes_timeout_when_token_configured(self, mock_get):
        mock_get.side_effect = [_ok([]), _ok({"voice_states": []})]
        response = self._call()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_get.call_count, 2)
        for call in mock_get.call_args_list:
            self.assertEqual(call.kwargs["timeout"], DISCORD_HTTP_TIMEOUT_S)


class UserGuildsTimeoutTest(TestCase):
    @patch("discordbot.services.users.requests.get")
    def test_passes_timeout(self, mock_get):
        from social_django.models import UserSocialAuth

        from discordbot.services.users import get_user_guilds

        user = CustomUser.objects.create_user(username="guilds-user", password="x")
        UserSocialAuth.objects.create(
            user=user, provider="discord", uid="42", extra_data={"access_token": "t"}
        )
        mock_get.return_value = _ok([])
        request = APIRequestFactory().get("/api/discord/user-guilds/")
        force_authenticate(request, user=user)

        response = get_user_guilds(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_get.call_args.kwargs["timeout"], DISCORD_HTTP_TIMEOUT_S)
