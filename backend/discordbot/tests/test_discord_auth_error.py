from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from discordbot.utils import DiscordAuthError, _rate_limited_request
from tests.test_auth import sync_discord_events_test
from tests.test_events_discord import send_test_notification


def _unauthorized_response() -> MagicMock:
    response = MagicMock(status_code=401)
    response.json.return_value = {"message": "401: Unauthorized", "code": 0}
    response.raise_for_status.side_effect = requests.HTTPError(
        "401 Client Error", response=response
    )
    return response


def _ok_response(data: dict[str, str]) -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = data
    response.raise_for_status.return_value = None
    return response


@patch("discordbot.utils._acquire_rate_limit_token", return_value=True)
class RateLimitedRequestAuthErrorTest(SimpleTestCase):
    @patch("discordbot.utils.requests.request")
    def test_401_raises_auth_error_without_retry(
        self, request: MagicMock, _token: MagicMock
    ) -> None:
        request.return_value = _unauthorized_response()

        with self.assertRaises(DiscordAuthError) as ctx:
            _rate_limited_request("GET", "https://discord.com/api/v10/users/@me")

        self.assertEqual(request.call_count, 1)
        self.assertEqual(ctx.exception.response.status_code, 401)

    def test_auth_error_is_a_request_exception(self, _token: MagicMock) -> None:
        self.assertTrue(issubclass(DiscordAuthError, requests.HTTPError))


@override_settings(DISCORD_BOT_TOKEN="rejected-token")
@patch("discordbot.utils._acquire_rate_limit_token", return_value=True)
@patch("discordbot.utils.internal_client.create_message_log")
@patch("discordbot.utils.requests.request")
class TestEndpointsDiscordAuthTest(SimpleTestCase):
    factory = APIRequestFactory()

    def _sync(self) -> Response:
        request = self.factory.post("/api/tests/events/sync-discord/")
        with patch("tests.test_auth.isTestEnvironment", return_value=True):
            return sync_discord_events_test(request)

    def _notify(self) -> Response:
        request = self.factory.post(
            "/api/tests/events/1/send-notification/",
            {"discord_user_id": "243497113906970625"},
            format="json",
        )
        with (
            patch("tests.test_events_discord.isTestEnvironment", return_value=True),
            patch("events.models.Event.objects") as events,
            patch(
                "events.discord.embeds.build_subscriber_dm_embed",
                return_value={"embed": {"title": "Event Reminder"}},
            ),
        ):
            events.select_related.return_value.get.return_value = MagicMock()
            return send_test_notification(request, 1)

    @patch("tests.test_auth.sync_discord_events", return_value="Scanned 1 events")
    def test_sync_returns_503_before_event_loop(
        self,
        sync: MagicMock,
        request: MagicMock,
        message_log: MagicMock,
        _token: MagicMock,
    ) -> None:
        request.return_value = _unauthorized_response()

        response = self._sync()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "discord_auth_failed")
        sync.assert_not_called()
        message_log.assert_not_called()

    @override_settings(DISCORD_BOT_TOKEN="")
    @patch("tests.test_auth.sync_discord_events", return_value="Scanned 0 events")
    def test_sync_without_token_keeps_running(
        self,
        sync: MagicMock,
        request: MagicMock,
        _message_log: MagicMock,
        _token: MagicMock,
    ) -> None:
        response = self._sync()

        self.assertEqual(response.status_code, 200)
        sync.assert_called_once()
        request.assert_not_called()

    def test_notification_returns_503_on_rejected_token(
        self, request: MagicMock, _message_log: MagicMock, _token: MagicMock
    ) -> None:
        request.return_value = _unauthorized_response()

        with override_settings(TEST=False):
            response = self._notify()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "discord_auth_failed")

    def test_notification_other_failure_stays_500(
        self, request: MagicMock, _message_log: MagicMock, _token: MagicMock
    ) -> None:
        def _discord(method: str, url: str, **kwargs: object) -> MagicMock:
            if url.endswith("/users/@me"):
                return _ok_response({"id": "bot"})
            response = MagicMock(status_code=403)
            response.json.return_value = {"code": 50007}
            response.raise_for_status.side_effect = requests.HTTPError(
                "403 Client Error", response=response
            )
            return response

        request.side_effect = _discord

        with override_settings(TEST=False):
            response = self._notify()

        self.assertEqual(response.status_code, 500)
        self.assertIn("DMs disabled", response.data["error"])
