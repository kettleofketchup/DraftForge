from unittest.mock import MagicMock, patch

from django.test import TestCase

from steam.tasks import (
    recalculate_user_league_mmr_task,
    sync_all_steam_leagues_task,
    sync_league_matches_task,
    update_league_stats_task,
)


class SyncLeagueMatchesTaskTest(TestCase):
    @patch("steam.tasks.SteamAPI")
    @patch("app.internal_client.requests.post")
    @patch("app.internal_client.requests.patch")
    @patch("app.internal_client.requests.get")
    def test_sync_skips_when_already_syncing(self, mock_get, mock_patch, mock_post, mock_api):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "league_id": 17929,
            "is_syncing": True,
            "last_match_id": None,
            "failed_match_ids": [],
        }
        mock_get.return_value = mock_resp

        result = sync_league_matches_task(17929)
        self.assertEqual(result["synced_count"], 0)
        mock_patch.assert_not_called()

    @patch("steam.tasks.update_league_stats_task")
    @patch("steam.tasks.SteamAPI")
    @patch("app.internal_client.requests.post")
    @patch("app.internal_client.requests.patch")
    @patch("app.internal_client.requests.get")
    def test_sync_stores_matches_via_api(self, mock_get, mock_patch, mock_post, mock_api, mock_stats_task):
        # GET sync-state returns not syncing
        get_resp = MagicMock()
        get_resp.ok = True
        get_resp.json.return_value = {
            "league_id": 17929,
            "is_syncing": False,
            "last_match_id": None,
            "failed_match_ids": [],
        }
        mock_get.return_value = get_resp

        # PATCH returns ok
        patch_resp = MagicMock()
        patch_resp.ok = True
        mock_patch.return_value = patch_resp

        # POST store-match returns created
        post_resp = MagicMock()
        post_resp.ok = True
        post_resp.status_code = 201
        post_resp.json.return_value = {
            "match_id": 123, "created": True, "players_stored": 10, "players_linked": 7
        }
        mock_post.return_value = post_resp

        # Steam API returns one match then empty
        api_instance = mock_api.return_value
        api_instance.get_match_history.side_effect = [
            {"result": {"matches": [{"match_id": 123, "match_seq_num": 456}]}},
            {"result": {"matches": []}},
        ]
        api_instance.get_match_history_by_seq_num.return_value = {
            "result": {"matches": [{"match_id": 123, "radiant_win": True, "duration": 2000,
                       "start_time": 0, "game_mode": 2, "lobby_type": 1, "players": []}]}
        }

        result = sync_league_matches_task(17929)
        self.assertEqual(result["synced_count"], 1)


class UpdateLeagueStatsTaskTest(TestCase):
    @patch("app.internal_client.requests.post")
    def test_calls_internal_api(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"updated_count": 5}
        mock_post.return_value = mock_resp

        result = update_league_stats_task(17929)
        self.assertEqual(result["updated_count"], 5)


class RecalculateMmrTaskTest(TestCase):
    @patch("app.internal_client.requests.post")
    def test_calls_internal_api(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"user_id": 1, "status": "recalculated"}
        mock_post.return_value = mock_resp

        result = recalculate_user_league_mmr_task(1)
        self.assertEqual(result["user_id"], 1)

    @patch("app.internal_client.requests.post")
    def test_returns_none_on_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_post.return_value = mock_resp

        result = recalculate_user_league_mmr_task(99999)
        self.assertIsNone(result)


class SyncAllSteamLeaguesTaskTest(TestCase):
    @patch("steam.tasks.sync_league_matches_task")
    @patch("app.internal_client.requests.get")
    def test_dispatches_one_subtask_per_tracked_league(self, mock_get, mock_subtask):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"steam_league_ids": [19571, 12345]}
        mock_get.return_value = mock_resp

        result = sync_all_steam_leagues_task()

        self.assertEqual(result, {
            "dispatched": 2,
            "league_ids": [19571, 12345],
        })
        self.assertEqual(mock_subtask.delay.call_count, 2)
        mock_subtask.delay.assert_any_call(19571)
        mock_subtask.delay.assert_any_call(12345)

    @patch("steam.tasks.sync_league_matches_task")
    @patch("app.internal_client.requests.get")
    def test_no_dispatch_when_no_leagues_configured(self, mock_get, mock_subtask):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"steam_league_ids": []}
        mock_get.return_value = mock_resp

        result = sync_all_steam_leagues_task()

        self.assertEqual(result, {"dispatched": 0, "league_ids": []})
        mock_subtask.delay.assert_not_called()

    @patch("steam.tasks.sync_league_matches_task")
    @patch("app.internal_client.requests.get")
    def test_retries_on_internal_api_failure(self, mock_get, mock_subtask):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "boom"
        mock_get.return_value = mock_resp

        # Celery's self.retry raises Retry; we just assert it bubbles up
        # and no sub-tasks were dispatched.
        from celery.exceptions import Retry

        with self.assertRaises(Retry):
            sync_all_steam_leagues_task()
        mock_subtask.delay.assert_not_called()
