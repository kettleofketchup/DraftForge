from unittest.mock import MagicMock, patch

from django.test import TestCase

from app.models import CustomUser
from steam.functions.league_sync import (
    link_user_to_stats,
    process_match,
    relink_all_users,
)
from steam.models import Match, PlayerMatchStats


class UserLinkingTest(TestCase):
    def setUp(self):
        self.match = Match.objects.create(
            match_id=7000000020,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )
        self.user = CustomUser.objects.create_user(
            username="linkedplayer",
            password="testpass123",
            steamid=76561198000000001,
        )

    def test_link_user_to_stats_success(self):
        stats = PlayerMatchStats.objects.create(
            match=self.match,
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
        linked = link_user_to_stats(stats)
        self.assertTrue(linked)
        stats.refresh_from_db()
        self.assertEqual(stats.user, self.user)

    def test_link_user_to_stats_no_match(self):
        stats = PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198999999999,  # No matching user
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
        linked = link_user_to_stats(stats)
        self.assertFalse(linked)
        stats.refresh_from_db()
        self.assertIsNone(stats.user)

    def test_relink_all_users(self):
        # Create stats without user link
        stats1 = PlayerMatchStats.objects.create(
            match=self.match,
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
        stats2 = PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198999999999,
            player_slot=1,
            hero_id=2,
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

        linked_count = relink_all_users()

        self.assertEqual(linked_count, 1)
        stats1.refresh_from_db()
        stats2.refresh_from_db()
        self.assertEqual(stats1.user, self.user)
        self.assertIsNone(stats2.user)


class ProcessMatchTest(TestCase):
    @patch("steam.functions.league_sync.SteamAPI")
    def test_process_match_success(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_match_details.return_value = {
            "result": {
                "match_id": 7000000030,
                "radiant_win": True,
                "duration": 2400,
                "start_time": 1704067200,
                "game_mode": 22,
                "lobby_type": 1,
                "players": [
                    {
                        "account_id": 40000001,
                        "player_slot": 0,
                        "hero_id": 1,
                        "kills": 10,
                        "deaths": 2,
                        "assists": 15,
                        "gold_per_min": 600,
                        "xp_per_min": 700,
                        "last_hits": 200,
                        "denies": 10,
                        "hero_damage": 25000,
                        "tower_damage": 5000,
                        "hero_healing": 0,
                    }
                ],
            }
        }
        mock_api_class.return_value = mock_api

        match = process_match(7000000030, league_id=17929)

        self.assertIsNotNone(match)
        self.assertEqual(match.match_id, 7000000030)
        self.assertEqual(match.league_id, 17929)
        self.assertEqual(match.players.count(), 1)

    @patch("steam.functions.league_sync.SteamAPI")
    def test_process_match_failure(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_match_details.return_value = None
        mock_api_class.return_value = mock_api

        match = process_match(7000000031, league_id=17929)

        self.assertIsNone(match)
