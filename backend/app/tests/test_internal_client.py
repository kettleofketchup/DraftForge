import os
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings


class InternalClientHeadersTest(TestCase):
    def test_headers_include_token(self):
        from app.internal_client.transport import headers

        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "my-token"}):
            h = headers()
        self.assertEqual(h["X-Internal-Token"], "my-token")
        self.assertEqual(h["Content-Type"], "application/json")

    def test_headers_with_empty_token(self):
        from app.internal_client.transport import headers

        with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": ""}):
            h = headers()
        self.assertEqual(h["X-Internal-Token"], "")


class InternalClientPostTest(TestCase):
    @patch("app.internal_client.transport.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_calls_correct_url(self, mock_post):
        mock_post.return_value = MagicMock(ok=True, status_code=201)
        from app.internal_client.transport import post

        post("/discord/message-log/", {"channel_id": "123"})
        args, kwargs = mock_post.call_args
        self.assertIn("/discord/message-log/", args[0])
        self.assertEqual(kwargs["json"]["channel_id"], "123")
        self.assertEqual(kwargs["timeout"], 30)

    @patch("app.internal_client.transport.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_returns_none_on_exception(self, mock_post):
        import requests as req

        mock_post.side_effect = req.RequestException("timeout")
        from app.internal_client.transport import post

        result = post("/test/", {})
        self.assertIsNone(result)

    @patch("app.internal_client.transport.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_returns_response_on_error_status(self, mock_post):
        """Non-200 returns the response (not None) — caller decides."""
        mock_post.return_value = MagicMock(
            ok=False, status_code=400, text="bad request"
        )
        from app.internal_client.transport import post

        result = post("/test/", {})
        self.assertIsNotNone(result)
        self.assertEqual(result.status_code, 400)


class InternalClientPatchTest(TestCase):
    @patch("app.internal_client.transport.requests.patch")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_patch_calls_correct_url(self, mock_patch):
        mock_patch.return_value = MagicMock(ok=True, status_code=200)
        from app.internal_client.transport import patch as patch_request

        patch_request("/discord/events/5/", {"scheduled_event_id": "999"})
        args, kwargs = mock_patch.call_args
        self.assertIn("/discord/events/5/", args[0])
        self.assertEqual(kwargs["json"]["scheduled_event_id"], "999")

    @patch("app.internal_client.transport.requests.patch")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_patch_returns_none_on_exception(self, mock_patch):
        import requests as req

        mock_patch.side_effect = req.RequestException("connection refused")
        from app.internal_client.transport import patch as patch_request

        result = patch_request("/test/", {})
        self.assertIsNone(result)


class InternalClientGetTest(TestCase):
    @patch("app.internal_client.transport.requests.get")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_get_calls_correct_url(self, mock_get):
        mock_get.return_value = MagicMock(ok=True, status_code=200)
        from app.internal_client.transport import get

        get("/events/1/")
        args, kwargs = mock_get.call_args
        self.assertIn("/events/1/", args[0])


class GetEventSignupsUnavailableTest(TestCase):
    """A failed signup read must raise, never look like an empty list."""

    @patch("app.internal_client.transport.requests.get")
    def test_error_status_raises(self, mock_get: MagicMock) -> None:
        from app.internal_client import InternalAPIUnavailable, get_event_signups

        resp = requests.Response()
        resp.status_code = 500
        resp._content = b"boom"
        mock_get.return_value = resp

        with self.assertRaises(InternalAPIUnavailable):
            get_event_signups(1)

    @patch("app.internal_client.transport.requests.get")
    def test_network_error_raises(self, mock_get: MagicMock) -> None:
        from app.internal_client import InternalAPIUnavailable, get_event_signups

        mock_get.side_effect = requests.ConnectionError("refused")

        with self.assertRaises(InternalAPIUnavailable):
            get_event_signups(1)

    @patch("app.internal_client.transport.requests.get")
    def test_empty_ok_response_is_an_empty_list(self, mock_get: MagicMock) -> None:
        from app.internal_client import get_event_signups

        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"[]"
        mock_get.return_value = resp

        self.assertEqual(get_event_signups(1), [])


class InternalClientConvenienceTest(TestCase):
    """Test that convenience functions call the right paths."""

    @patch("app.internal_client.transport.post")
    def test_create_message_log(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        from app.internal_client import create_message_log

        create_message_log(channel_id="123", source="test", source_id=1)
        mock_post.assert_called_once_with(
            "/discord/message-log/",
            {"channel_id": "123", "source": "test", "source_id": 1},
        )

    @patch("app.internal_client.transport.post")
    def test_create_event_log(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        from app.internal_client import create_event_log

        create_event_log(discord_event_id=5, action="test", target_type="X")
        mock_post.assert_called_once_with(
            "/discord/event-log/",
            {"discord_event_id": 5, "action": "test", "target_type": "X"},
        )

    @patch("app.internal_client.transport.patch")
    def test_update_discord_event(self, mock_patch):
        mock_patch.return_value = MagicMock(ok=True)
        from app.internal_client import update_discord_event

        update_discord_event(5, scheduled_event_id="999")
        mock_patch.assert_called_once_with(
            "/discord/events/5/",
            {"scheduled_event_id": "999"},
        )

    @patch("app.internal_client.transport.post")
    def test_transition_event_state(self, mock_post):
        mock_post.return_value = MagicMock(ok=True)
        from app.internal_client import transition_event_state

        transition_event_state(1, "signups_open")
        mock_post.assert_called_once_with(
            "/events/1/transition/",
            {"state": "signups_open"},
        )


class InternalClientAuthRoundTripTest(TestCase):
    """The client's request, served by the real internal view and auth class."""

    def _serve(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: int | None = None,
    ) -> MagicMock:
        from app.internal_client.transport import INTERNAL_API_URL

        path = "/api/internal" + url.removeprefix(INTERNAL_API_URL)
        resp = self.client.get(path, data=params or {}, headers=headers)
        return MagicMock(
            ok=resp.status_code < 400,
            status_code=resp.status_code,
            text=resp.content.decode(),
        )

    def _status_with(self, client_token: str, server_token: str) -> int:
        from app.internal_client.transport import get

        with (
            patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": client_token}),
            override_settings(INTERNAL_SERVICE_TOKEN=server_token),
            patch(
                "app.internal_client.transport.requests.get", side_effect=self._serve
            ),
        ):
            return get("/steam/tracked-leagues/").status_code

    def test_matching_token_is_accepted(self) -> None:
        self.assertEqual(self._status_with("shared-token", "shared-token"), 200)

    def test_unset_token_on_both_sides_is_rejected(self) -> None:
        self.assertEqual(self._status_with("", ""), 403)

    def test_mismatched_token_is_rejected(self) -> None:
        self.assertEqual(self._status_with("worker-token", "backend-token"), 403)
