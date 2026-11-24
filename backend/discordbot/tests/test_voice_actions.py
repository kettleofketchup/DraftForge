from __future__ import annotations

from typing import Any
from unittest import mock

from django.test import SimpleTestCase

from discordbot.internal_client import voice_actions

TRANSPORT = "discordbot.internal_client.voice_actions.transport"

GET_FALLBACK: dict[str, Any] = {"available": False, "channels": [], "ttl_seconds": 60}
POST_FALLBACK: dict[str, Any] = {
    "success": False,
    "detail": "internal_api_unreachable",
    "events": 0,
    "joined": 0,
    "left": 0,
    "confirmed": 0,
    "unknown_users": 0,
    "not_signed_up": 0,
}


def _ok(payload: Any) -> mock.Mock:
    resp = mock.Mock(ok=True)
    resp.json.return_value = payload
    return resp


def _bad_json() -> mock.Mock:
    resp = mock.Mock(ok=True, text="x")
    resp.json.side_effect = ValueError
    return resp


def _failures() -> list[mock.Mock | None]:
    return [None, mock.Mock(ok=False), _bad_json()]


def _report() -> dict[str, Any]:
    return voice_actions.report_voice_state(
        guild_id="111",
        discord_user_id="222",
        before_channel_id=None,
        after_channel_id="333",
    )


def _snapshot() -> dict[str, Any]:
    return voice_actions.post_voice_snapshot(
        guild_id="111",
        channels=[{"channel_id": "333", "member_ids": ["222"]}],
        missing_channel_ids=["444"],
    )


class WatchedChannelsClientTests(SimpleTestCase):
    def test_failures_return_fallback(self) -> None:
        for resp in _failures():
            with self.subTest(resp=resp), mock.patch(TRANSPORT) as transport:
                transport.get.return_value = resp
                self.assertEqual(voice_actions.get_watched_channels(), GET_FALLBACK)

    def test_fallback_is_fresh_copy(self) -> None:
        with mock.patch(TRANSPORT) as transport:
            transport.get.return_value = None
            first = voice_actions.get_watched_channels()
            first["channels"].append("x")
            self.assertEqual(voice_actions.get_watched_channels(), GET_FALLBACK)

    def test_ok_response_validated(self) -> None:
        payload = {
            "channels": [{"guild_id": "111", "channel_id": "333", "event_ids": [5, 7]}],
            "ttl_seconds": 60,
            "extra": "ignored",
        }
        with mock.patch(TRANSPORT) as transport:
            transport.get.return_value = _ok(payload)
            result = voice_actions.get_watched_channels()
        transport.get.assert_called_once_with("/discord/voice/watched-channels/")
        self.assertIs(result["available"], True)
        self.assertEqual(
            result["channels"],
            [{"guild_id": "111", "channel_id": "333", "event_ids": [5, 7]}],
        )
        self.assertEqual(result["ttl_seconds"], 60)
        self.assertNotIn("extra", result)


class ReportVoiceStateClientTests(SimpleTestCase):
    def test_failures_return_fallback(self) -> None:
        for resp in _failures():
            with self.subTest(resp=resp), mock.patch(TRANSPORT) as transport:
                transport.post.return_value = resp
                self.assertEqual(_report(), POST_FALLBACK)

    def test_ok_response_validated_and_body_posted(self) -> None:
        payload = {"success": True, "detail": "", "events": 1, "joined": 1}
        with mock.patch(TRANSPORT) as transport:
            transport.post.return_value = _ok(payload)
            result = _report()
        transport.post.assert_called_once_with(
            "/discord/voice/state/",
            {
                "guild_id": "111",
                "discord_user_id": "222",
                "before_channel_id": None,
                "after_channel_id": "333",
            },
        )
        self.assertEqual(
            result,
            {**POST_FALLBACK, "success": True, "detail": "", "events": 1, "joined": 1},
        )


class PostVoiceSnapshotClientTests(SimpleTestCase):
    def test_failures_return_fallback(self) -> None:
        for resp in _failures():
            with self.subTest(resp=resp), mock.patch(TRANSPORT) as transport:
                transport.post.return_value = resp
                self.assertEqual(_snapshot(), POST_FALLBACK)

    def test_ok_response_validated_and_body_posted(self) -> None:
        payload = {"success": True, "detail": "", "events": 2, "left": 1}
        with mock.patch(TRANSPORT) as transport:
            transport.post.return_value = _ok(payload)
            result = _snapshot()
        transport.post.assert_called_once_with(
            "/discord/voice/snapshot/",
            {
                "guild_id": "111",
                "channels": [{"channel_id": "333", "member_ids": ["222"]}],
                "missing_channel_ids": ["444"],
            },
        )
        self.assertEqual(
            result,
            {**POST_FALLBACK, "success": True, "detail": "", "events": 2, "left": 1},
        )
