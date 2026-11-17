from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings

from discordbot.services.discord_members import (
    DiscordMembersFetchError,
    get_discord_members_data,
)

GUILD = "555"
CACHE_KEY = f"discord_members_{GUILD}"


def _resp(
    status: int,
    payload: Any = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock(status_code=status)
    resp.headers = headers or {}
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _members(start: int, count: int) -> list[dict]:
    return [{"user": {"id": str(i)}} for i in range(start, start + count)]


@override_settings(
    DISCORD_BOT_TOKEN="t",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test_discord_members_fetch",
        }
    },
)
class GuildMemberFetchTest(TestCase):
    def setUp(self) -> None:
        cache.clear()

    @patch("discordbot.services.discord_members.requests.get")
    def test_force_skips_cache_read_and_rewrites(self, mock_get: MagicMock) -> None:
        cache.set(CACHE_KEY, [{"old": 1}])
        fetched = _members(1, 2)
        mock_get.return_value = _resp(200, fetched)

        self.assertEqual(get_discord_members_data(GUILD, force=True), fetched)
        self.assertEqual(cache.get(CACHE_KEY), fetched)

    @patch("discordbot.services.discord_members.requests.get")
    def test_write_cache_false_leaves_cache_untouched(
        self, mock_get: MagicMock
    ) -> None:
        cache.set(CACHE_KEY, [{"old": 1}])
        fetched = _members(1, 2)
        mock_get.return_value = _resp(200, fetched)

        result = get_discord_members_data(GUILD, force=True, write_cache=False)

        self.assertEqual(result, fetched)
        self.assertEqual(cache.get(CACHE_KEY), [{"old": 1}])

    @patch("discordbot.services.discord_members.time.sleep")
    @patch("discordbot.services.discord_members.requests.get")
    def test_429_retry_after_honoured_once(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        fetched = _members(1, 3)
        mock_get.side_effect = [
            _resp(429, {"retry_after": 0.01}),
            _resp(200, fetched),
        ]

        self.assertEqual(get_discord_members_data(GUILD), fetched)
        mock_sleep.assert_called_once_with(0.01)

    @patch("discordbot.services.discord_members.time.sleep")
    @patch("discordbot.services.discord_members.requests.get")
    def test_429_retry_after_header_fallback(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        fetched = _members(1, 1)
        bad_json = _resp(429, None, {"Retry-After": "2"})
        bad_json.json.side_effect = ValueError("not json")
        mock_get.side_effect = [bad_json, _resp(200, fetched)]

        self.assertEqual(get_discord_members_data(GUILD), fetched)
        mock_sleep.assert_called_once_with(2.0)

    @patch("discordbot.services.discord_members.time.sleep")
    @patch("discordbot.services.discord_members.requests.get")
    def test_429_twice_raises(self, mock_get: MagicMock, mock_sleep: MagicMock) -> None:
        mock_get.side_effect = [
            _resp(429, {"retry_after": 0.01}),
            _resp(429, {"retry_after": 0.01}),
        ]

        with self.assertRaises(DiscordMembersFetchError):
            get_discord_members_data(GUILD)
        mock_sleep.assert_called_once_with(0.01)
        self.assertIsNone(cache.get(CACHE_KEY))

    @patch("discordbot.services.discord_members.time.sleep")
    @patch("discordbot.services.discord_members.requests.get")
    def test_429_retry_after_over_10s_raises(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_get.return_value = _resp(429, {"retry_after": 30})

        with self.assertRaises(DiscordMembersFetchError):
            get_discord_members_data(GUILD)
        mock_sleep.assert_not_called()

    @patch("discordbot.services.discord_members.requests.get")
    def test_second_page_failure_raises_and_caches_nothing(
        self, mock_get: MagicMock
    ) -> None:
        mock_get.side_effect = [
            _resp(200, _members(1, 1000)),
            requests.RequestException("boom"),
        ]

        with self.assertRaises(DiscordMembersFetchError):
            get_discord_members_data(GUILD)
        self.assertIsNone(cache.get(CACHE_KEY))

    @patch("discordbot.services.discord_members.requests.get")
    def test_http_error_raises_typed_error(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _resp(403, {"message": "Missing Access"})

        with self.assertRaises(DiscordMembersFetchError):
            get_discord_members_data(GUILD)
