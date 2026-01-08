import pytest
from django.conf import settings
from django.test import TestCase, override_settings

from app.models import CustomUser, PositionsModel
from steam.functions.mmr_calculation import (
    calculate_mmr_adjustment,
    get_league_avg_gpm,
    get_league_avg_kda,
    update_user_league_mmr,
)
from steam.models import LeaguePlayerStats


class TestMMRCalculation(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass",
            mmr=4000,
            positions=self.positions,
        )

    def test_calculate_mmr_adjustment_below_min_games(self):
        """Should return 0 if below minimum games threshold."""
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=2,
            wins=2,
            losses=0,
            win_rate=1.0,
            avg_kills=15,
            avg_deaths=2,
            avg_assists=10,
            avg_gpm=600,
            avg_xpm=700,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertEqual(adjustment, 0)

    @override_settings(LEAGUE_MMR_MIN_GAMES=5)
    def test_calculate_mmr_adjustment_high_performer(self):
        """High win rate and stats should give positive adjustment."""
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=20,
            wins=14,
            losses=6,
            win_rate=0.7,
            avg_kills=10,
            avg_deaths=4,
            avg_assists=12,
            avg_gpm=550,
            avg_xpm=600,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertGreater(adjustment, 0)
        self.assertLessEqual(adjustment, 500)

    @override_settings(LEAGUE_MMR_MIN_GAMES=5)
    def test_calculate_mmr_adjustment_low_performer(self):
        """Low win rate and stats should give negative adjustment."""
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=20,
            wins=6,
            losses=14,
            win_rate=0.3,
            avg_kills=3,
            avg_deaths=9,
            avg_assists=5,
            avg_gpm=350,
            avg_xpm=400,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertLess(adjustment, 0)
        self.assertGreaterEqual(adjustment, -500)

    @override_settings(LEAGUE_MMR_MIN_GAMES=5)
    def test_calculate_mmr_adjustment_clamped_to_range(self):
        """Adjustment should be clamped between -500 and +500."""
        # Create a baseline player with average stats to establish league average
        baseline_positions = PositionsModel.objects.create()
        baseline_user = CustomUser.objects.create_user(
            username="baseline_player",
            password="testpass",
            mmr=3000,
            positions=baseline_positions,
        )
        LeaguePlayerStats.objects.create(
            user=baseline_user,
            league_id=12345,
            games_played=20,
            wins=10,
            losses=10,
            win_rate=0.5,
            avg_kills=5,
            avg_deaths=5,
            avg_assists=5,
            avg_gpm=400,
            avg_xpm=450,
        )

        # Extreme high performer - stats far above the league baseline
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=50,
            wins=50,
            losses=0,
            win_rate=1.0,
            avg_kills=20,
            avg_deaths=1,
            avg_assists=15,
            avg_gpm=800,
            avg_xpm=900,
        )
        adjustment = calculate_mmr_adjustment(stats)
        # Should be clamped to 500 (would be higher without clamping)
        self.assertEqual(adjustment, 500)

    def test_update_user_league_mmr(self):
        """Should set league_mmr to base mmr + best adjustment."""
        LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=10,
            mmr_adjustment=150,
        )
        LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=67890,
            games_played=10,
            mmr_adjustment=200,
        )
        update_user_league_mmr(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.league_mmr, 4200)  # 4000 + 200

    def test_update_user_league_mmr_no_base_mmr(self):
        """Should set league_mmr to None if user has no base mmr."""
        self.user.mmr = None
        self.user.save()
        update_user_league_mmr(self.user)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.league_mmr)
