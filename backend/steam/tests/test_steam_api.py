from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, TestCase

from app.models import CustomUser
from steam.utils.steam_api_caller import SteamAPI, SteamAPIKeyMissing


class SteamAPIMethodsTest(TestCase):
    def setUp(self):
        self.api = SteamAPI(api_key="test_key")

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_get_match_history(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {"status": 1, "matches": [{"match_id": 123}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.api.get_match_history(league_id=17929)

        self.assertIn("result", result)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn("league_id", call_args.kwargs.get("params", {}))

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_get_match_history_with_pagination(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"matches": []}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        self.api.get_match_history(league_id=17929, start_at_match_id=123456)

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params", {})
        self.assertEqual(params.get("start_at_match_id"), 123456)

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_get_live_league_games(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"games": [{"match_id": 789}]}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.api.get_live_league_games(league_id=17929)

        self.assertIn("result", result)


class SteamAPIPlayerSummariesTest(SimpleTestCase):
    def setUp(self) -> None:
        self.api = SteamAPI(api_key="test_key")

    def _ok(self, payload: dict[str, Any]) -> MagicMock:
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status = MagicMock()
        return response

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_get_player_summaries_url_and_params(self, mock_get: MagicMock) -> None:
        mock_get.return_value = self._ok({"response": {"players": []}})

        result = self.api.get_player_summaries(
            CustomUser.STEAM_ID_64_BASE + 123, timeout=(1.0, 1.5)
        )

        self.assertEqual(result, {"response": {"players": []}})
        args, kwargs = mock_get.call_args
        self.assertEqual(
            args[0],
            "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
        )
        self.assertEqual(kwargs["params"]["steamids"], str(76561197960265728 + 123))
        self.assertEqual(kwargs["timeout"], (1.0, 1.5))

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_get_player_summaries_joins_list(self, mock_get: MagicMock) -> None:
        mock_get.return_value = self._ok({"response": {"players": []}})

        self.api.get_player_summaries([1, 2])

        self.assertEqual(mock_get.call_args.kwargs["params"]["steamids"], "1,2")

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_get_player_summaries_skips_throttle(self, mock_get: MagicMock) -> None:
        mock_get.return_value = self._ok({"response": {"players": []}})

        with (
            patch("steam.utils.retry.get_request_lock") as lock,
            patch.object(SteamAPI, "_request") as throttled,
        ):
            self.api.get_player_summaries(1)

        lock.assert_not_called()
        throttled.assert_not_called()
        mock_get.assert_called_once()

    @patch("steam.utils.steam_api_caller.requests.get")
    def test_request_still_throttled(self, mock_get: MagicMock) -> None:
        mock_get.return_value = self._ok({"result": {}})

        with patch("steam.utils.retry.get_request_lock") as lock:
            lock.return_value = MagicMock()
            self.api.get_match_details(1)

        lock.assert_called_once()
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 10)


class SteamAPIKeyRedactionTest(SimpleTestCase):
    @patch("steam.utils.steam_api_caller.log")
    @patch("steam.utils.steam_api_caller.requests.get")
    def test_connection_error_log_omits_key(
        self, mock_get: MagicMock, mock_log: MagicMock
    ) -> None:
        mock_get.side_effect = requests.exceptions.ConnectionError(
            "Max retries exceeded with url: "
            "/ISteamUser/GetPlayerSummaries/v2/?key=test_key&steamids=1"
        )

        result = SteamAPI(api_key="test_key").get_player_summaries(1)

        self.assertIsNone(result)
        mock_log.warning.assert_called_once()
        for call in mock_log.mock_calls:
            for value in [*call.args, *call.kwargs.values()]:
                self.assertNotIn("test_key", str(value))
        self.assertIn("key=***", mock_log.warning.call_args.kwargs["error"])

    def test_missing_key_raises_dedicated_error(self) -> None:
        with patch.dict("os.environ", {"STEAM_API_KEY": ""}):
            with self.assertRaises(SteamAPIKeyMissing):
                SteamAPI()
            with self.assertRaises(ValueError):
                SteamAPI()
