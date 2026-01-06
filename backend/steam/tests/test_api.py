from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser
from steam.constants import LEAGUE_ID
from steam.models import GameMatchSuggestion, LeagueSyncState, Match, PlayerMatchStats


class SyncLeagueEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = CustomUser.objects.create_user(
            username="staff", password="testpass123", is_staff=True
        )
        self.regular_user = CustomUser.objects.create_user(
            username="regular", password="testpass123"
        )

    @patch("steam.functions.api.sync_league_matches")
    def test_sync_league_as_staff(self, mock_sync):
        """Test sync endpoint as staff user."""
        mock_sync.return_value = {
            "synced_count": 10,
            "failed_count": 2,
            "new_last_match_id": 888001,
        }

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_sync"), {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["synced_count"], 10)
        mock_sync.assert_called_once_with(LEAGUE_ID, full_sync=False)

    @patch("steam.functions.api.sync_league_matches")
    def test_sync_league_full_sync(self, mock_sync):
        """Test sync endpoint with full_sync=True."""
        mock_sync.return_value = {
            "synced_count": 100,
            "failed_count": 5,
            "new_last_match_id": 999001,
        }

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            reverse("steam_sync"), {"full_sync": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_sync.assert_called_once_with(LEAGUE_ID, full_sync=True)

    @patch("steam.functions.api.sync_league_matches")
    def test_sync_league_custom_league_id(self, mock_sync):
        """Test sync endpoint with custom league_id."""
        mock_sync.return_value = {
            "synced_count": 5,
            "failed_count": 0,
            "new_last_match_id": 123456,
        }

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            reverse("steam_sync"), {"league_id": 12345}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_sync.assert_called_once_with(12345, full_sync=False)

    def test_sync_league_as_regular_user(self):
        """Test sync endpoint denied for non-staff."""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(reverse("steam_sync"), {})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sync_league_unauthenticated(self):
        """Test sync endpoint denied for unauthenticated."""
        response = self.client.post(reverse("steam_sync"), {})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RetryFailedEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = CustomUser.objects.create_user(
            username="staff", password="testpass123", is_staff=True
        )

    @patch("steam.functions.api.retry_failed_matches")
    def test_retry_failed_as_staff(self, mock_retry):
        """Test retry failed endpoint as staff."""
        mock_retry.return_value = {
            "synced_count": 3,
            "failed_count": 1,
            "new_last_match_id": None,
        }

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_retry_failed"), {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_retry.assert_called_once_with(LEAGUE_ID)

    def test_retry_failed_unauthenticated(self):
        """Test retry failed endpoint denied for unauthenticated."""
        response = self.client.post(reverse("steam_retry_failed"), {})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RelinkUsersEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = CustomUser.objects.create_user(
            username="staff", password="testpass123", is_staff=True
        )

    @patch("steam.functions.api.relink_all_users")
    def test_relink_all_users(self, mock_relink):
        """Test relink all users endpoint."""
        mock_relink.return_value = 15

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_relink_users"), {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["linked_count"], 15)
        mock_relink.assert_called_once()

    @patch("steam.functions.api.link_user_to_stats")
    def test_relink_specific_matches(self, mock_link):
        """Test relink specific matches."""
        # Create a match and stats to relink
        match = Match.objects.create(
            match_id=123456,
            radiant_win=True,
            duration=2400,
            start_time=1700000000,
            game_mode=22,
            lobby_type=1,
            league_id=LEAGUE_ID,
        )
        from steam.models import PlayerMatchStats

        stats = PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=5,
            deaths=3,
            assists=10,
            gold_per_min=500,
            xp_per_min=600,
            last_hits=200,
            denies=10,
            hero_damage=15000,
            tower_damage=2000,
            hero_healing=0,
        )

        mock_link.return_value = True

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            reverse("steam_relink_users"), {"match_ids": [123456]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["linked_count"], 1)

    def test_relink_users_unauthenticated(self):
        """Test relink users endpoint denied for unauthenticated."""
        response = self.client.post(reverse("steam_relink_users"), {})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FindByPlayersEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("steam.functions.api.find_matches_by_players")
    def test_find_by_players(self, mock_find):
        """Test find by players endpoint."""
        mock_find.return_value = Match.objects.none()

        response = self.client.post(
            reverse("steam_find_by_players"),
            {"steam_ids": [76561198000000001, 76561198000000002]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_find.assert_called_once_with(
            [76561198000000001, 76561198000000002], require_all=True, league_id=None
        )

    @patch("steam.functions.api.find_matches_by_players")
    def test_find_by_players_any_match(self, mock_find):
        """Test find by players with require_all=False."""
        mock_find.return_value = Match.objects.none()

        response = self.client.post(
            reverse("steam_find_by_players"),
            {
                "steam_ids": [76561198000000001, 76561198000000002],
                "require_all": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_find.assert_called_once_with(
            [76561198000000001, 76561198000000002], require_all=False, league_id=None
        )

    def test_find_by_players_empty_list(self):
        """Test find by players with empty list returns error."""
        response = self.client.post(
            reverse("steam_find_by_players"), {"steam_ids": []}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_find_by_players_missing_steam_ids(self):
        """Test find by players without steam_ids returns error."""
        response = self.client.post(reverse("steam_find_by_players"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LiveGamesEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("steam.functions.api.SteamAPI")
    def test_get_live_games(self, mock_api_class):
        """Test get live games endpoint."""
        mock_api = mock_api_class.return_value
        mock_api.get_live_league_games.return_value = {
            "result": {"games": [{"match_id": 123, "players": []}]}
        }

        response = self.client.get(reverse("steam_live_games"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("games", response.data)

    @patch("steam.functions.api.SteamAPI")
    def test_get_live_games_empty(self, mock_api_class):
        """Test get live games when no games are live."""
        mock_api = mock_api_class.return_value
        mock_api.get_live_league_games.return_value = None

        response = self.client.get(reverse("steam_live_games"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"games": []})

    @patch("steam.functions.api.SteamAPI")
    def test_get_live_games_with_league_id(self, mock_api_class):
        """Test get live games with custom league_id."""
        mock_api = mock_api_class.return_value
        mock_api.get_live_league_games.return_value = {"result": {"games": []}}

        response = self.client.get(reverse("steam_live_games"), {"league_id": "12345"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_api.get_live_league_games.assert_called_once_with(league_id=12345)


class SyncStatusEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_sync_status_no_state(self):
        """Test sync status with no existing state."""
        response = self.client.get(reverse("steam_sync_status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["league_id"], LEAGUE_ID)
        self.assertIsNone(response.data["last_sync_at"])
        self.assertFalse(response.data["is_syncing"])

    def test_sync_status_with_state(self):
        """Test sync status with existing state."""
        LeagueSyncState.objects.create(
            league_id=LEAGUE_ID, last_match_id=777001, is_syncing=True
        )

        response = self.client.get(reverse("steam_sync_status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["last_match_id"], 777001)
        self.assertTrue(response.data["is_syncing"])

    def test_sync_status_with_failed_matches(self):
        """Test sync status showing failed match count."""
        LeagueSyncState.objects.create(
            league_id=LEAGUE_ID,
            last_match_id=777001,
            failed_match_ids=[111, 222, 333],
        )

        response = self.client.get(reverse("steam_sync_status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["failed_match_count"], 3)


class AutoLinkEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = CustomUser.objects.create_user(
            username="staff", password="testpass123", is_staff=True
        )
        self.regular_user = CustomUser.objects.create_user(
            username="regular", password="testpass123"
        )

    @patch("steam.functions.api.auto_link_matches_for_tournament")
    def test_auto_link_as_staff(self, mock_auto_link):
        """Test auto-link endpoint as staff."""
        mock_auto_link.return_value = {
            "auto_linked_count": 5,
            "suggestions_created_count": 3,
        }

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            reverse("steam_auto_link"), {"tournament_id": 1}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["auto_linked_count"], 5)
        self.assertEqual(response.data["suggestions_created_count"], 3)

    def test_auto_link_missing_tournament_id(self):
        """Test auto-link with missing tournament_id returns error."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_auto_link"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_auto_link_as_regular_user(self):
        """Test auto-link endpoint denied for non-staff."""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            reverse("steam_auto_link"), {"tournament_id": 1}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_auto_link_unauthenticated(self):
        """Test auto-link endpoint denied for unauthenticated."""
        response = self.client.post(
            reverse("steam_auto_link"), {"tournament_id": 1}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SuggestionEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = CustomUser.objects.create_user(
            username="staff", password="testpass123", is_staff=True
        )
        self.regular_user = CustomUser.objects.create_user(
            username="regular", password="testpass123"
        )

    @patch("steam.functions.api.get_suggestions_for_tournament")
    def test_get_tournament_suggestions(self, mock_get):
        """Test getting tournament suggestions."""
        mock_get.return_value = GameMatchSuggestion.objects.none()

        response = self.client.get(reverse("steam_tournament_suggestions", args=[1]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once_with(1)

    @patch("steam.functions.api.get_suggestions_for_game")
    def test_get_game_suggestions(self, mock_get):
        """Test getting game suggestions."""
        mock_get.return_value = GameMatchSuggestion.objects.none()

        response = self.client.get(reverse("steam_game_suggestions", args=[42]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once_with(42)

    @patch("steam.functions.api.confirm_suggestion")
    def test_confirm_suggestion_as_staff(self, mock_confirm):
        """Test confirming suggestion as staff."""
        mock_confirm.return_value = True

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_confirm_suggestion", args=[1]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "confirmed")
        mock_confirm.assert_called_once_with(1)

    @patch("steam.functions.api.confirm_suggestion")
    def test_confirm_suggestion_not_found(self, mock_confirm):
        """Test confirming non-existent suggestion."""
        mock_confirm.return_value = False

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_confirm_suggestion", args=[999]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_confirm_suggestion_as_regular_user(self):
        """Test confirm suggestion denied for non-staff."""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(reverse("steam_confirm_suggestion", args=[1]))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("steam.functions.api.dismiss_suggestion")
    def test_dismiss_suggestion_as_staff(self, mock_dismiss):
        """Test dismissing suggestion as staff."""
        mock_dismiss.return_value = True

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_dismiss_suggestion", args=[1]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "dismissed")
        mock_dismiss.assert_called_once_with(1)

    @patch("steam.functions.api.dismiss_suggestion")
    def test_dismiss_suggestion_not_found(self, mock_dismiss):
        """Test dismissing non-existent suggestion."""
        mock_dismiss.return_value = False

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("steam_dismiss_suggestion", args=[999]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_dismiss_suggestion_as_regular_user(self):
        """Test dismiss suggestion denied for non-staff."""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(reverse("steam_dismiss_suggestion", args=[1]))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dismiss_suggestion_unauthenticated(self):
        """Test dismiss suggestion denied for unauthenticated."""
        response = self.client.post(reverse("steam_dismiss_suggestion", args=[1]))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MatchDetailViewTest(TestCase):
    def setUp(self):
        self.match = Match.objects.create(
            match_id=99999,
            radiant_win=True,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=7,
        )
        PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=5,
            deaths=3,
            assists=10,
            gold_per_min=500,
            xp_per_min=600,
            last_hits=150,
            denies=5,
            hero_damage=20000,
            tower_damage=2000,
            hero_healing=0,
        )

    def test_get_match_detail(self):
        response = self.client.get("/api/steam/matches/99999/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["match_id"], 99999)
        self.assertEqual(len(data["players"]), 1)
        self.assertEqual(data["players"][0]["hero_id"], 1)

    def test_get_match_not_found(self):
        response = self.client.get("/api/steam/matches/1/")
        self.assertEqual(response.status_code, 404)
