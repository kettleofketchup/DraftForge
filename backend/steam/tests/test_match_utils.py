from django.test import TestCase

from steam.functions.match_utils import find_matches_by_players
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
