import time
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.db import transaction
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from app.models import CustomUser
from steam.services import account_lookup
from steam.services.account_lookup import (
    STEAM_ACCOUNT_FOUND_TTL,
    STEAM_ACCOUNT_MISSING_TTL,
    SteamLookupRateLimited,
    cached_exists_key,
    ensure_steam_account_exists,
    steam_account_exists,
)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ACCOUNT_ID = 123


def _api(payload: Any = None, side_effect: BaseException | None = None) -> MagicMock:
    api_cls = MagicMock()
    method = api_cls.return_value.get_player_summaries
    if side_effect is not None:
        method.side_effect = side_effect
    else:
        method.return_value = payload
    return api_cls


def _failure_reasons(log: MagicMock) -> list[str]:
    return [
        c.kwargs["reason"]
        for c in log.warning.call_args_list
        if c.args and c.args[0] == "steam_account_lookup_failed"
    ]


@override_settings(STEAM_ACCOUNT_LOOKUP_ENABLED=True, CACHES=LOCMEM)
class SteamAccountExistsTest(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()
        log_patcher = patch.object(account_lookup, "log")
        self.log = log_patcher.start()
        self.addCleanup(log_patcher.stop)

    def _run(self, api_cls: MagicMock, account_id: int = ACCOUNT_ID) -> bool | None:
        with patch.object(account_lookup, "SteamAPI", api_cls):
            return steam_account_exists(account_id)

    def test_found_true_cached_one_hour(self) -> None:
        api_cls = _api({"response": {"players": [{}]}})
        with patch.object(account_lookup.cache, "set", wraps=cache.set) as spy:
            self.assertIs(self._run(api_cls), True)
        self.assertIs(cache.get(cached_exists_key(ACCOUNT_ID)), True)
        self.assertEqual(spy.call_args.args[2], STEAM_ACCOUNT_FOUND_TTL)
        self.assertEqual(STEAM_ACCOUNT_FOUND_TTL, 3600)
        steamids = api_cls.return_value.get_player_summaries.call_args.args[0]
        self.assertEqual(steamids, ACCOUNT_ID + CustomUser.STEAM_ID_64_BASE)
        self.assertEqual(
            api_cls.return_value.get_player_summaries.call_args.kwargs["timeout"],
            (1.0, 1.5),
        )

    def test_empty_false_cached_fifteen_min(self) -> None:
        with patch.object(account_lookup.cache, "set", wraps=cache.set) as spy:
            self.assertIs(self._run(_api({"response": {"players": []}})), False)
        self.assertIs(cache.get(cached_exists_key(ACCOUNT_ID)), False)
        self.assertEqual(spy.call_args.args[2], STEAM_ACCOUNT_MISSING_TTL)
        self.assertEqual(STEAM_ACCOUNT_MISSING_TTL, 900)

    def _assert_fail_open(self, api_cls: MagicMock) -> None:
        self.assertIsNone(self._run(api_cls))
        self.assertIsNone(cache.get(cached_exists_key(ACCOUNT_ID)))
        self.assertEqual(len(_failure_reasons(self.log)), 1)
        self.assertTrue(_failure_reasons(self.log)[0])

    def test_http_none_fails_open_not_cached(self) -> None:
        self._assert_fail_open(_api(None))

    def test_missing_key_fails_open(self) -> None:
        api_cls = MagicMock(side_effect=ValueError("no key"))
        self._assert_fail_open(api_cls)

    def test_json_decode_error_fails_open(self) -> None:
        err = requests.exceptions.JSONDecodeError("bad", "doc", 0)
        self._assert_fail_open(_api(side_effect=err))

    def test_malformed_body_fails_open(self) -> None:
        self._assert_fail_open(_api({"foo": 1}))

    def test_players_not_a_list_fails_open(self) -> None:
        self._assert_fail_open(_api({"response": {"players": "x"}}))

    def test_budget_timeout_fails_open(self) -> None:
        api_cls = MagicMock()

        def slow(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            time.sleep(0.3)
            return {"response": {"players": [{}]}}

        api_cls.return_value.get_player_summaries.side_effect = slow
        with patch.object(account_lookup, "STEAM_ACCOUNT_LOOKUP_BUDGET_S", 0.05):
            self._assert_fail_open(api_cls)
        self.assertEqual(_failure_reasons(self.log), ["timeout"])

    def test_cache_hit_no_http(self) -> None:
        cache.set(cached_exists_key(ACCOUNT_ID), True, 60)
        api_cls = _api({"response": {"players": []}})
        self.assertIs(self._run(api_cls), True)
        api_cls.assert_not_called()

    @override_settings(STEAM_ACCOUNT_LOOKUP_ENABLED=False)
    def test_disabled_returns_none_no_http(self) -> None:
        cache.set(cached_exists_key(ACCOUNT_ID), True, 60)
        api_cls = _api({"response": {"players": [{}]}})
        self.assertIsNone(self._run(api_cls))
        api_cls.assert_not_called()

    def test_cache_only_miss_returns_none_no_http(self) -> None:
        api_cls = _api({"response": {"players": [{}]}})
        with patch.object(account_lookup, "SteamAPI", api_cls):
            self.assertIsNone(steam_account_exists(ACCOUNT_ID, cache_only=True))
            cache.set(cached_exists_key(ACCOUNT_ID), False, 60)
            self.assertIs(steam_account_exists(ACCOUNT_ID, cache_only=True), False)
        api_cls.assert_not_called()

    def test_user_budget_raises_after_ten(self) -> None:
        user = CustomUser(pk=4242)
        api_cls = _api({"response": {"players": [{}]}})
        with patch.object(account_lookup, "SteamAPI", api_cls):
            for i in range(10):
                self.assertIs(
                    ensure_steam_account_exists(1000 + i, budget_user=user), True
                )
            with self.assertRaises(SteamLookupRateLimited):
                ensure_steam_account_exists(2000, budget_user=user)
            self.assertIs(ensure_steam_account_exists(1000, budget_user=user), True)
            self.assertIs(
                ensure_steam_account_exists(3000, budget_user=CustomUser(pk=4243)),
                True,
            )
        self.assertEqual(api_cls.return_value.get_player_summaries.call_count, 11)

    def test_global_cap_fails_open(self) -> None:
        api_cls = _api({"response": {"players": [{}]}})
        with (
            patch.object(account_lookup, "GLOBAL_LOOKUP_LIMIT", 2),
            patch.object(account_lookup, "SteamAPI", api_cls),
        ):
            self.assertIs(steam_account_exists(1), True)
            self.assertIs(
                ensure_steam_account_exists(2, budget_user=CustomUser(pk=1)), True
            )
            self.assertIsNone(steam_account_exists(3))
        self.assertEqual(api_cls.return_value.get_player_summaries.call_count, 2)
        self.assertIsNone(cache.get(cached_exists_key(3)))
        events = [c.args[0] for c in self.log.warning.call_args_list]
        self.assertIn("steam_account_lookup_budget_exhausted", events)


@override_settings(STEAM_ACCOUNT_LOOKUP_ENABLED=True, CACHES=LOCMEM)
class SteamAccountExistsAtomicTest(TransactionTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_in_atomic_block_miss_no_http(self) -> None:
        api_cls = _api({"response": {"players": [{}]}})
        with (
            patch.object(account_lookup, "SteamAPI", api_cls),
            patch.object(account_lookup, "log") as log,
        ):
            with transaction.atomic():
                self.assertIsNone(steam_account_exists(ACCOUNT_ID))
                self.assertIsNone(
                    ensure_steam_account_exists(
                        ACCOUNT_ID, budget_user=CustomUser(pk=7)
                    )
                )
            api_cls.assert_not_called()
            errors = [c.args[0] for c in log.error.call_args_list]
            self.assertEqual(errors.count("steam_account_lookup_in_atomic"), 2)

            self.assertIs(steam_account_exists(ACCOUNT_ID), True)
            api_cls.return_value.get_player_summaries.assert_called_once()

            with transaction.atomic():
                self.assertIs(steam_account_exists(ACCOUNT_ID), True)
