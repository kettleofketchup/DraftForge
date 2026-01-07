from django.test import TestCase

from app.models import CustomUser, PositionsModel
from steam.functions.stats_update import update_player_league_stats
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats


class TestStatsUpdate(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass",
            steamid=76561198000000001,
            mmr=4000,
            positions=self.positions,
        )
        self.league_id = 12345

    def test_update_player_league_stats_creates_new(self):
        """Should create LeaguePlayerStats if doesn't exist."""
        # Create a match and player stats
        match = Match.objects.create(
            match_id=1001,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=self.league_id,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            user=self.user,
            player_slot=0,  # Radiant
            hero_id=1,
            kills=10,
            deaths=3,
            assists=15,
            gold_per_min=550,
            xp_per_min=600,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=0,
        )

        update_player_league_stats(self.user, self.league_id)

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=self.league_id)
        self.assertEqual(stats.games_played, 1)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 0)
        self.assertEqual(stats.total_kills, 10)
        self.assertEqual(stats.avg_kills, 10.0)

    def test_update_player_league_stats_accumulates(self):
        """Should accumulate stats from multiple matches."""
        # Create two matches
        for i, (radiant_win, player_slot) in enumerate([(True, 0), (False, 0)]):
            match = Match.objects.create(
                match_id=1001 + i,
                radiant_win=radiant_win,
                duration=2400,
                start_time=1704067200 + i * 3600,
                game_mode=22,
                lobby_type=1,
                league_id=self.league_id,
            )
            PlayerMatchStats.objects.create(
                match=match,
                steam_id=76561198000000001,
                user=self.user,
                player_slot=player_slot,
                hero_id=1,
                kills=10,
                deaths=5,
                assists=10,
                gold_per_min=500,
                xp_per_min=550,
                last_hits=180,
                denies=8,
                hero_damage=20000,
                tower_damage=2000,
                hero_healing=0,
            )

        update_player_league_stats(self.user, self.league_id)

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=self.league_id)
        self.assertEqual(stats.games_played, 2)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 1)
        self.assertEqual(stats.win_rate, 0.5)
        self.assertEqual(stats.total_kills, 20)
        self.assertEqual(stats.avg_kills, 10.0)
