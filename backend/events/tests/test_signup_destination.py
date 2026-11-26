from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings
from structlog.testing import capture_logs

from discordbot import utils
from events.discord.signup_destination import resolve_signup_channel_type


@override_settings(DISCORD_BOT_TOKEN="test-token")
class SignupDestinationTest(SimpleTestCase):
    def resolve(self, payload: Any) -> int | None:
        response = MagicMock()
        response.json.return_value = payload
        with patch.object(utils, "_rate_limited_request", return_value=response):
            return resolve_signup_channel_type("C", "G")

    @patch.object(utils, "_rate_limited_request")
    def test_supported_types_use_authenticated_rate_limited_get(
        self, request: MagicMock
    ) -> None:
        for kind in (0, 5, 15):
            with self.subTest(kind=kind):
                request.return_value.json.return_value = {
                    "id": "C",
                    "guild_id": "G",
                    "type": kind,
                }
                self.assertEqual(resolve_signup_channel_type("C", "G"), kind)
                request.assert_called_once_with(
                    "GET",
                    f"{utils.DISCORD_API_BASE}/channels/C",
                    headers={
                        "Authorization": "Bot test-token",
                        "Content-Type": "application/json",
                    },
                )
                request.reset_mock()

    def test_rejects_invalid_metadata(self) -> None:
        for kind in (None, "0", True, False, 1, 2, 10, 16):
            with self.subTest(kind=kind):
                self.assertIsNone(
                    self.resolve({"id": "C", "guild_id": "G", "type": kind})
                )
        for payload in (None, [], "secret", 0, {"id": "C", "guild_id": "G"}):
            with self.subTest(payload=payload):
                self.assertIsNone(self.resolve(payload))

    def test_rejects_wrong_identity(self) -> None:
        for payload in (
            {"guild_id": "G", "type": 0},
            {"id": "other", "guild_id": "G", "type": 0},
            {"id": "C", "type": 0},
            {"id": "C", "guild_id": "other", "type": 0},
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(self.resolve(payload))
        with patch.object(utils, "_rate_limited_request") as request:
            self.assertIsNone(resolve_signup_channel_type("C", ""))
            request.assert_not_called()

    @patch.object(utils, "_rate_limited_request")
    def test_http_and_transport_failures_return_none(self, request: MagicMock) -> None:
        for status in (401, 403, 404, 429, 500):
            with self.subTest(status=status):
                response = requests.Response()
                response.status_code = status
                request.return_value = response
                self.assertIsNone(resolve_signup_channel_type("C", "G"))
        for error in (
            requests.ConnectionError("secret"),
            requests.Timeout("secret"),
            utils.DiscordAuthError("secret"),
            utils.DiscordRateLimitTimeout("secret"),
        ):
            with self.subTest(error=type(error)):
                request.side_effect = error
                self.assertIsNone(resolve_signup_channel_type("C", "G"))

    @patch.object(utils, "_rate_limited_request")
    def test_invalid_json_returns_none(self, request: MagicMock) -> None:
        request.return_value.json.side_effect = requests.exceptions.JSONDecodeError(
            "bad", "x", 0
        )
        self.assertIsNone(resolve_signup_channel_type("C", "G"))

    @patch.object(utils, "_rate_limited_request", side_effect=TypeError("bug"))
    def test_programming_error_propagates(self, request: MagicMock) -> None:
        with self.assertRaises(TypeError):
            resolve_signup_channel_type("C", "G")

    @patch.object(
        utils,
        "_rate_limited_request",
        side_effect=requests.Timeout("private-body test-token"),
    )
    def test_warning_does_not_include_sensitive_response(
        self, request: MagicMock
    ) -> None:
        with capture_logs() as logs:
            self.assertIsNone(resolve_signup_channel_type("C", "G"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["system"], "events")
        self.assertEqual(logs[0]["subsystem"], "discord")
        self.assertEqual(logs[0]["channel_id"], "C")
        self.assertNotIn("test-token", str(logs))
        self.assertNotIn("private-body", str(logs))
