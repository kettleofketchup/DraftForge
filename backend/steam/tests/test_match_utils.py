from datetime import date
from unittest.mock import patch

from django.test import TestCase

from app.models import CustomUser, Team, Tournament
from steam.functions.match_utils import (
    find_live_game_by_players,
    find_matches_by_players,
    find_matches_by_team,
)
from steam.models import Match, PlayerMatchStats


class FindMatchesByPlayersTest(TestCase):
    def setUp(self):
        # Create match with 3 players
        self.match1 = Match.objects.create(
            match_id=7000000500,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        for i, steam_id in enumerate(
            [76561198000000001, 76561198000000002, 76561198000000003]
        ):
            PlayerMatchStats.objects.create(
                match=self.match1,
                steam_id=steam_id,
                player_slot=i,
                hero_id=i + 1,
                kills=10,
                deaths=2,
                assists=15,
                gold_per_min=600,
                xp_per_min=700,
                last_hits=200,
                denies=10,
                hero_damage=25000,
                tower_damage=5000,
                hero_healing=0,
            )

        # Create another match with different players
        self.match2 = Match.objects.create(
            match_id=7000000501,
            radiant_win=False,
            duration=1800,
            start_time=1704070800,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        for i, steam_id in enumerate([76561198000000004, 76561198000000005]):
            PlayerMatchStats.objects.create(
                match=self.match2,
                steam_id=steam_id,
                player_slot=i,
                hero_id=i + 1,
                kills=5,
                deaths=5,
                assists=10,
                gold_per_min=400,
                xp_per_min=500,
                last_hits=100,
                denies=5,
                hero_damage=15000,
                tower_damage=2000,
                hero_healing=0,
            )

    def test_find_matches_require_all(self):
        steam_ids = [76561198000000001, 76561198000000002]
        matches = find_matches_by_players(steam_ids, require_all=True)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first(), self.match1)

    def test_find_matches_require_any(self):
        steam_ids = [76561198000000001, 76561198000000004]
        matches = find_matches_by_players(steam_ids, require_all=False)
        self.assertEqual(matches.count(), 2)

    def test_find_matches_with_league_filter(self):
        # Create match in different league
        match3 = Match.objects.create(
            match_id=7000000502,
            radiant_win=True,
            duration=2400,
            start_time=1704074400,
            game_mode=22,
            lobby_type=1,
            league_id=12345,
        )
        PlayerMatchStats.objects.create(
            match=match3,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=5000,
            hero_healing=0,
        )

        steam_ids = [76561198000000001]
        matches = find_matches_by_players(steam_ids, league_id=17929)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first().league_id, 17929)


class FindMatchesByTeamTest(TestCase):
    def setUp(self):
        # Create a tournament (required for Team)
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date(2024, 1, 1)
        )

        # Create team with members who have steamids
        self.user1 = CustomUser.objects.create_user(
            username="team_player1", discordId="1001", steamid=76561198000000001
        )
        self.user2 = CustomUser.objects.create_user(
            username="team_player2", discordId="1002", steamid=76561198000000002
        )
        self.user_no_steam = CustomUser.objects.create_user(
            username="no_steam_player", discordId="1003"
        )

        self.team = Team.objects.create(name="Test Team", tournament=self.tournament)
        self.team.members.add(self.user1, self.user2, self.user_no_steam)

        # Create match with team players
        self.match = Match.objects.create(
            match_id=999001,
            radiant_win=True,
            duration=2400,
            start_time=1700000000,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000001,
            hero_id=1,
            kills=5,
            deaths=2,
            assists=10,
            player_slot=0,
            gold_per_min=500,
            xp_per_min=600,
            last_hits=150,
            denies=5,
            hero_damage=20000,
            tower_damage=3000,
            hero_healing=0,
        )
        PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000002,
            hero_id=2,
            kills=3,
            deaths=4,
            assists=8,
            player_slot=1,
            gold_per_min=450,
            xp_per_min=550,
            last_hits=120,
            denies=3,
            hero_damage=15000,
            tower_damage=2000,
            hero_healing=0,
        )

    def test_find_matches_by_team(self):
        """Test finding matches by team members."""
        matches = find_matches_by_team(self.team.id)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first().match_id, 999001)

    def test_find_matches_by_team_not_found(self):
        """Test with non-existent team."""
        matches = find_matches_by_team(99999)
        self.assertEqual(matches.count(), 0)

    def test_find_matches_by_team_no_steamids(self):
        """Test team with no steamid members."""
        empty_team = Team.objects.create(
            name="Empty Steam Team", tournament=self.tournament
        )
        empty_team.members.add(self.user_no_steam)

        matches = find_matches_by_team(empty_team.id)
        self.assertEqual(matches.count(), 0)


class FindLiveGameByPlayersTest(TestCase):
    @patch("steam.utils.steam_api_caller.SteamAPI")
    def test_find_live_game_with_player(self, mock_api_class):
        """Test finding live game with matching player."""
        mock_api = mock_api_class.return_value
        # account_id = steam_id_64 - 76561197960265728
        # For steam_id 76561198000000001: account_id = 39734273
        mock_api.get_live_league_games.return_value = {
            "result": {
                "games": [
                    {
                        "match_id": 12345,
                        "players": [
                            {"account_id": 39734273},
                            {"account_id": 100000},
                        ],
                    }
                ]
            }
        }

        result = find_live_game_by_players([76561198000000001])

        self.assertIsNotNone(result)
        self.assertEqual(result["match_id"], 12345)

    @patch("steam.utils.steam_api_caller.SteamAPI")
    def test_find_live_game_no_match(self, mock_api_class):
        """Test no matching player in live games."""
        mock_api = mock_api_class.return_value
        mock_api.get_live_league_games.return_value = {
            "result": {
                "games": [{"match_id": 12345, "players": [{"account_id": 100000}]}]
            }
        }

        result = find_live_game_by_players([76561198000000001])

        self.assertIsNone(result)

    @patch("steam.utils.steam_api_caller.SteamAPI")
    def test_find_live_game_empty_steam_ids(self, mock_api_class):
        """Test with empty steam_ids list."""
        result = find_live_game_by_players([])

        self.assertIsNone(result)
        mock_api_class.assert_not_called()

    @patch("steam.utils.steam_api_caller.SteamAPI")
    def test_find_live_game_api_error(self, mock_api_class):
        """Test handling of API error response."""
        mock_api = mock_api_class.return_value
        mock_api.get_live_league_games.return_value = None

        result = find_live_game_by_players([76561198000000001])

        self.assertIsNone(result)
