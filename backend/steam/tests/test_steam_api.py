from unittest.mock import MagicMock, patch

from django.test import TestCase

from steam.utils.steam_api_caller import SteamAPI


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
