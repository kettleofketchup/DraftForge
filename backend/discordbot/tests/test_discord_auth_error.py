from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from discordbot.dm import DMOutcome
from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.utils import DiscordAuthError, _rate_limited_request
from tests.test_auth import sync_discord_events_test
from tests.test_events_discord import discord_status, send_test_notification


def _unauthorized_response() -> MagicMock:
    response = MagicMock(status_code=401)
    response.json.return_value = {"message": "401: Unauthorized", "code": 0}
    response.raise_for_status.side_effect = requests.HTTPError(
        "401 Client Error", response=response
    )
    return response


GRANTED = ClaimResult(
    id=7, granted=True, status=DMStatus.PENDING, attempts=1, created=True
)
EMBED = {"title": "Event Reminder"}


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
@patch("discordbot.dm.finalize_dm", return_value=True)
@patch("discordbot.dm.mark_dm_sending", return_value=True)
@patch("discordbot.dm.claim_dm", return_value=GRANTED)
@patch("discordbot.utils._acquire_rate_limit_token", return_value=True)
@patch("discordbot.utils.internal_client.create_message_log")
@patch("discordbot.utils.requests.request")
class TestEndpointsDiscordAuthTest(SimpleTestCase):
    factory = APIRequestFactory()

    def _sync(self) -> Response:
        request = self.factory.post("/api/tests/events/sync-discord/")
        with patch("tests.test_auth.isTestEnvironment", return_value=True):
            return sync_discord_events_test(request)

    def _notify(self, *, test_env: bool = True) -> Response:
        request = self.factory.post(
            "/api/tests/events/1/send-notification/",
            {"discord_user_id": "243497113906970625"},
            format="json",
        )
        with (
            patch("tests.test_events_discord.isTestEnvironment", return_value=test_env),
            patch("tests.test_events_discord.Event.objects") as events,
            patch(
                "tests.test_events_discord.build_subscriber_dm_embed",
                return_value={"embed": EMBED},
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
        _claim: MagicMock,
        _mark: MagicMock,
        _finalize: MagicMock,
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
        _claim: MagicMock,
        _mark: MagicMock,
        _finalize: MagicMock,
    ) -> None:
        response = self._sync()

        self.assertEqual(response.status_code, 200)
        sync.assert_called_once()
        request.assert_not_called()

    def test_notification_returns_503_on_rejected_token(
        self,
        request: MagicMock,
        _message_log: MagicMock,
        _token: MagicMock,
        _claim: MagicMock,
        _mark: MagicMock,
        finalize: MagicMock,
    ) -> None:
        request.return_value = _unauthorized_response()

        with override_settings(TEST=False):
            response = self._notify()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "discord_auth_failed")
        finalize.assert_called_once()
        self.assertEqual(finalize.call_args.args[1].status, DMStatus.FAILED.value)

    def test_notification_other_failure_stays_500(
        self,
        request: MagicMock,
        _message_log: MagicMock,
        _token: MagicMock,
        _claim: MagicMock,
        _mark: MagicMock,
        finalize: MagicMock,
    ) -> None:
        def _discord(method: str, url: str, **kwargs: object) -> MagicMock:
            if url.endswith("/users/@me"):
                return _ok_response({"id": "bot"})
            response = requests.Response()
            response.status_code = 403
            response.url = url
            response._content = b'{"code": 50007, "message": "Cannot send messages"}'
            return response

        request.side_effect = _discord

        with override_settings(TEST=False):
            response = self._notify()

        self.assertEqual(response.status_code, 500)
        self.assertIn("DMs disabled", response.data["error"])
        self.assertEqual(finalize.call_args.args[1].error_code, 50007)

    def test_send_test_notification_uses_send_dm(
        self,
        _request: MagicMock,
        _message_log: MagicMock,
        _token: MagicMock,
        _claim: MagicMock,
        _mark: MagicMock,
        _finalize: MagicMock,
    ) -> None:
        outcome = DMOutcome(
            status=DMStatus.SENT,
            ledger_id=7,
            message_id="msg-77",
            channel_id="chan-7",
            error_code=None,
        )
        with patch(
            "tests.test_events_discord.send_dm", return_value=outcome
        ) as send_dm:
            response = self._notify()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data), {"success", "message_id", "embed", "components"}
        )
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message_id"], "msg-77")
        self.assertEqual(response.data["embed"], EMBED)
        req = send_dm.call_args.args[0]
        self.assertEqual(req.kind, DMKind.TEST_NOTIFICATION)
        self.assertEqual(req.subject, (DMSubject.EVENT, 1))
        self.assertEqual(req.discord_user_id, "243497113906970625")
        self.assertTrue(
            req.idempotency_key.startswith(
                "test_notification:event:1:discord:243497113906970625:req:"
            )
        )

    def test_notification_ledger_unavailable_returns_503(
        self,
        request: MagicMock,
        _message_log: MagicMock,
        _token: MagicMock,
        claim: MagicMock,
        _mark: MagicMock,
        _finalize: MagicMock,
    ) -> None:
        claim.return_value = None

        with override_settings(TEST=False):
            response = self._notify()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"error": "dm_ledger_unavailable"})
        request.assert_not_called()

    def test_notification_not_found_outside_tests(
        self,
        request: MagicMock,
        _message_log: MagicMock,
        _token: MagicMock,
        claim: MagicMock,
        _mark: MagicMock,
        _finalize: MagicMock,
    ) -> None:
        response = self._notify(test_env=False)

        self.assertEqual(response.status_code, 404)
        claim.assert_not_called()


class DiscordStatusEndpointTest(SimpleTestCase):
    factory = APIRequestFactory()

    def _status(self) -> Response:
        request = self.factory.get("/api/tests/discord/status/")
        with patch("tests.test_events_discord.isTestEnvironment", return_value=True):
            return discord_status(request)

    @override_settings(DISCORD_BOT_TOKEN="a-token")
    def test_reports_configured_token(self) -> None:
        self.assertEqual(self._status().data, {"bot_token_configured": True})

    @override_settings(DISCORD_BOT_TOKEN=None)
    def test_reports_missing_token(self) -> None:
        self.assertEqual(self._status().data, {"bot_token_configured": False})

    def test_not_found_outside_tests(self) -> None:
        request = self.factory.get("/api/tests/discord/status/")
        with patch("tests.test_events_discord.isTestEnvironment", return_value=False):
            self.assertEqual(discord_status(request).status_code, 404)
