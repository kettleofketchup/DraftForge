import json
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.http import JsonResponse
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from social_django.models import UserSocialAuth

from app.models import CustomUser
from discordbot.services.users import (
    DISCORD_HTTP_TIMEOUT_S,
    _user_guilds_cache_key,
    get_user_guilds,
)


def _ok(payload: object) -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = payload
    return response


class UserGuildsCacheTest(TestCase):
    user_a: CustomUser
    user_b: CustomUser
    social_a: UserSocialAuth
    factory: APIRequestFactory
    keys: list[str]

    def setUp(self) -> None:
        self.user_a = CustomUser.objects.create_user(username="guild-cache-a")
        self.user_b = CustomUser.objects.create_user(username="guild-cache-b")
        self.social_a = UserSocialAuth.objects.create(
            user=self.user_a,
            provider="discord",
            uid="1001",
            extra_data={"access_token": "token-a"},
        )
        UserSocialAuth.objects.create(
            user=self.user_b,
            provider="discord",
            uid="1002",
            extra_data={"access_token": "token-b"},
        )
        self.factory = APIRequestFactory()
        self.keys = [
            _user_guilds_cache_key(self.user_a.pk, "1001"),
            _user_guilds_cache_key(self.user_b.pk, "1002"),
            _user_guilds_cache_key(self.user_a.pk, "1003"),
            "discord_guilds",
        ]
        cache.delete_many(self.keys)
        self.addCleanup(cache.delete_many, self.keys)

    def _call(self, user: CustomUser | None) -> JsonResponse | Response:
        request = self.factory.get("/api/discord/guilds/")
        if user is not None:
            force_authenticate(request, user=user)
        return get_user_guilds(request)

    @patch("discordbot.services.users.requests.get")
    def test_second_user_gets_own_guilds(self, mock_get: MagicMock) -> None:
        guild_a = [{"id": "1", "name": "Guild A"}]
        guild_b = [{"id": "2", "name": "Guild B"}]
        mock_get.side_effect = [_ok(guild_a), _ok(guild_b)]
        for user, expected in [
            (self.user_a, guild_a),
            (self.user_b, guild_b),
            (self.user_a, guild_a),
        ]:
            response = self._call(user)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.content), {"guilds": expected})
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(
            mock_get.call_args_list[1].kwargs["headers"],
            {"Authorization": "Bearer token-b"},
        )
        self.assertEqual(
            mock_get.call_args_list[1].kwargs["timeout"], DISCORD_HTTP_TIMEOUT_S
        )

    @patch("discordbot.services.users.requests.get")
    def test_same_user_served_from_cache(self, mock_get: MagicMock) -> None:
        guilds = [{"id": "1", "name": "Guild A"}]
        mock_get.return_value = _ok(guilds)
        with patch("discordbot.services.users.cache.set", wraps=cache.set) as spy:
            first = self._call(self.user_a)
            second = self._call(self.user_a)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(json.loads(first.content), {"guilds": guilds})
        self.assertEqual(json.loads(second.content), json.loads(first.content))
        self.assertEqual(mock_get.call_count, 1)
        spy.assert_called_once_with(self.keys[0], guilds, timeout=5)

    @patch("discordbot.services.users.requests.get")
    def test_empty_list_is_cached(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _ok([])
        for _ in range(2):
            response = self._call(self.user_a)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.content), {"guilds": []})
        self.assertEqual(mock_get.call_count, 1)

    @patch("discordbot.services.users.requests.get")
    def test_relinked_discord_account_not_served_old_guilds(
        self, mock_get: MagicMock
    ) -> None:
        old = [{"id": "1", "name": "Old"}]
        new = [{"id": "3", "name": "New"}]
        mock_get.side_effect = [_ok(old), _ok(new)]
        self._call(self.user_a)
        self.social_a.uid = "1003"
        self.social_a.extra_data = {"access_token": "token-a2"}
        self.social_a.save()
        response = self._call(self.user_a)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"guilds": new})
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(
            mock_get.call_args.kwargs["headers"], {"Authorization": "Bearer token-a2"}
        )

    @patch("discordbot.services.users.requests.get")
    def test_legacy_global_key_ignored(self, mock_get: MagicMock) -> None:
        foreign = [{"id": "9", "name": "Foreign"}]
        own = [{"id": "1", "name": "Guild A"}]
        cache.set("discord_guilds", foreign, timeout=60)
        mock_get.return_value = _ok(own)
        response = self._call(self.user_a)
        self.assertEqual(json.loads(response.content), {"guilds": own})
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(cache.get("discord_guilds"), foreign)

    def _assert_safe_warning(
        self, mock_log: MagicMock, status_code: int | None
    ) -> None:
        mock_log.warning.assert_called_once_with(
            "discord_user_guilds_failed",
            system="discord",
            subsystem="oauth_guilds",
            user_id=self.user_a.pk,
            status_code=status_code,
        )

    def _assert_bad_gateway(self, response: JsonResponse | Response) -> None:
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            json.loads(response.content), {"error": "Failed to fetch Discord guilds"}
        )

    @patch("discordbot.services.users.log")
    @patch("discordbot.services.users.requests.get")
    def test_error_not_cached_and_not_echoed(
        self, mock_get: MagicMock, mock_log: MagicMock
    ) -> None:
        guilds = [{"id": "1", "name": "Guild A"}]
        mock_get.side_effect = [
            requests.exceptions.RequestException("secret detail token-a"),
            _ok(guilds),
        ]
        first = self._call(self.user_a)
        self._assert_bad_gateway(first)
        self.assertNotIn(b"secret detail", first.content)
        self.assertNotIn(b"token-a", first.content)
        self._assert_safe_warning(mock_log, None)
        second = self._call(self.user_a)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(json.loads(second.content), {"guilds": guilds})
        self.assertEqual(mock_get.call_count, 2)

    @patch("discordbot.services.users.log")
    @patch("discordbot.services.users.requests.get")
    def test_http_error_logs_status_without_token(
        self, mock_get: MagicMock, mock_log: MagicMock
    ) -> None:
        upstream = MagicMock(status_code=401)
        failing = MagicMock(status_code=401)
        failing.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "401 token-a", response=upstream
        )
        mock_get.return_value = failing
        response = self._call(self.user_a)
        self._assert_bad_gateway(response)
        self.assertNotIn(b"token-a", response.content)
        self._assert_safe_warning(mock_log, 401)

    @patch("discordbot.services.users.requests.get")
    def test_non_list_payload_not_cached(self, mock_get: MagicMock) -> None:
        guilds = [{"id": "1", "name": "Guild A"}]
        for payload in ({"message": "nope"}, None):
            with self.subTest(payload=payload):
                cache.delete(self.keys[0])
                mock_get.reset_mock()
                mock_get.side_effect = [_ok(payload), _ok(guilds)]
                self._assert_bad_gateway(self._call(self.user_a))
                response = self._call(self.user_a)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(json.loads(response.content), {"guilds": guilds})
                self.assertEqual(mock_get.call_count, 2)

    @patch("discordbot.services.users.requests.get")
    def test_invalid_json_not_cached(self, mock_get: MagicMock) -> None:
        guilds = [{"id": "1", "name": "Guild A"}]
        broken = MagicMock(status_code=200)
        broken.json.side_effect = requests.exceptions.JSONDecodeError("invalid", "", 0)
        mock_get.side_effect = [broken, _ok(guilds)]
        self._assert_bad_gateway(self._call(self.user_a))
        response = self._call(self.user_a)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"guilds": guilds})
        self.assertEqual(mock_get.call_count, 2)

    def _assert_not_linked(self, response: JsonResponse | Response) -> None:
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.content), {"error": "Discord account not linked"}
        )

    @patch("discordbot.services.users.requests.get")
    def test_missing_social_auth_returns_400(self, mock_get: MagicMock) -> None:
        cache.set(self.keys[0], [{"id": "1", "name": "Guild A"}], timeout=60)
        self.social_a.delete()
        self._assert_not_linked(self._call(self.user_a))
        mock_get.assert_not_called()

    @patch("discordbot.services.users.requests.get")
    def test_missing_access_token_returns_400(self, mock_get: MagicMock) -> None:
        cache.set(self.keys[0], [{"id": "1", "name": "Guild A"}], timeout=60)
        for extra_data in ({}, {"access_token": ""}, {"access_token": None}):
            with self.subTest(extra_data=extra_data):
                self.social_a.extra_data = extra_data
                self.social_a.save()
                self._assert_not_linked(self._call(self.user_a))
        mock_get.assert_not_called()

    @patch("discordbot.services.users.requests.get")
    def test_anonymous_cannot_read_cached_guilds(self, mock_get: MagicMock) -> None:
        cache.set(self.keys[0], [{"id": "1", "name": "Guild A"}], timeout=60)
        response = self._call(None)
        self.assertIn(response.status_code, (401, 403))
        mock_get.assert_not_called()

    def test_key_excludes_token(self) -> None:
        key = _user_guilds_cache_key(self.user_a.pk, "1001")
        self.assertEqual(key, f"discord_user_guilds:{self.user_a.pk}:1001")
        self.assertNotIn("token-a", key)
        self.assertNotIn("token-b", key)
        self.assertNotEqual(key, _user_guilds_cache_key(self.user_b.pk, "1001"))
        self.assertNotEqual(key, _user_guilds_cache_key(self.user_a.pk, "1002"))
