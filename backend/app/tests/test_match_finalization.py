"""Tests for match finalization service."""

from datetime import timedelta

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    League,
    LeagueMatch,
    LeagueMatchParticipant,
    LeagueRating,
    Organization,
)


class MatchFinalizationServiceTest(TestCase):
    """Test LeagueMatchService.finalize()."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin", password="testpass123"
        )
        self.org = Organization.objects.create(name="Test Org")
        self.org.admins.add(self.admin)
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name="Test League",
            rating_system="elo",
            k_factor_default=32.0,
        )

        # Create 10 players (5v5)
        self.radiant = []
        self.dire = []
        for i in range(5):
            p = CustomUser.objects.create_user(username=f"radiant{i}", password="test")
            p.mmr = 3000
            p.save()
            self.radiant.append(p)

        for i in range(5):
            p = CustomUser.objects.create_user(username=f"dire{i}", password="test")
            p.mmr = 3000
            p.save()
            self.dire.append(p)

    def test_finalize_creates_ratings_if_missing(self):
        """Finalize should create LeagueRating records for new players."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        LeagueMatchService.finalize(
            match=match, winners=self.radiant, losers=self.dire, winning_side="radiant"
        )

        # All 10 players should have ratings now
        self.assertEqual(LeagueRating.objects.filter(league=self.league).count(), 10)

    def test_finalize_updates_ratings(self):
        """Finalize should update winner/loser ratings correctly."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        LeagueMatchService.finalize(
            match=match, winners=self.radiant, losers=self.dire, winning_side="radiant"
        )

        # Winners should have positive_stats increased
        winner_rating = LeagueRating.objects.get(
            league=self.league, player=self.radiant[0]
        )
        self.assertGreater(winner_rating.positive_stats, 0)
        self.assertEqual(winner_rating.negative_stats, 0)
        self.assertEqual(winner_rating.wins, 1)
        self.assertEqual(winner_rating.games_played, 1)

        # Losers should have negative_stats increased
        loser_rating = LeagueRating.objects.get(league=self.league, player=self.dire[0])
        self.assertEqual(loser_rating.positive_stats, 0)
        self.assertGreater(loser_rating.negative_stats, 0)
        self.assertEqual(loser_rating.losses, 1)
        self.assertEqual(loser_rating.games_played, 1)

    def test_finalize_creates_participants(self):
        """Finalize should create LeagueMatchParticipant records."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        LeagueMatchService.finalize(
            match=match, winners=self.radiant, losers=self.dire, winning_side="radiant"
        )

        # Should have 10 participants
        self.assertEqual(match.participants.count(), 10)

        # Check participant data
        winner_part = match.participants.get(player=self.radiant[0])
        self.assertTrue(winner_part.is_winner)
        self.assertEqual(winner_part.team_side, "radiant")
        self.assertGreater(winner_part.delta, 0)
        self.assertEqual(winner_part.mmr_at_match, 3000)

        loser_part = match.participants.get(player=self.dire[0])
        self.assertFalse(loser_part.is_winner)
        self.assertEqual(loser_part.team_side, "dire")
        self.assertLess(loser_part.delta, 0)

    def test_finalize_marks_match_finalized(self):
        """Finalize should set is_finalized and finalized_at."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        LeagueMatchService.finalize(
            match=match, winners=self.radiant, losers=self.dire, winning_side="radiant"
        )

        match.refresh_from_db()
        self.assertTrue(match.is_finalized)
        self.assertIsNotNone(match.finalized_at)

    def test_finalize_already_finalized_raises(self):
        """Cannot finalize an already finalized match."""
        from app.services.match_finalization import LeagueMatchService

        match = LeagueMatch.objects.create(
            league=self.league,
            played_at=timezone.now(),
            is_finalized=True,
            finalized_at=timezone.now(),
        )

        with self.assertRaises(ValueError) as ctx:
            LeagueMatchService.finalize(
                match=match,
                winners=self.radiant,
                losers=self.dire,
                winning_side="radiant",
            )

        self.assertIn("already finalized", str(ctx.exception))

    def test_finalize_with_existing_rating(self):
        """Finalize should work when some players already have ratings."""
        from app.services.match_finalization import LeagueMatchService

        # Create a rating for one player
        LeagueRating.objects.create(
            league=self.league, player=self.radiant[0], base_mmr=3000
        )

        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        # Should succeed without error
        LeagueMatchService.finalize(
            match=match, winners=self.radiant, losers=self.dire, winning_side="radiant"
        )

        # Should have created participants
        self.assertEqual(match.participants.count(), 10)


class AgeDecayCalculationTest(TestCase):
    """Test age decay calculations."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin", password="testpass123"
        )
        self.org = Organization.objects.create(name="Test Org")
        self.org.admins.add(self.admin)
        self.league = League.objects.create(
            organization=self.org,
            steam_league_id=12345,
            name="Test League",
            age_decay_enabled=True,
            age_decay_half_life_days=180,
            age_decay_minimum=0.1,
        )

    def test_no_decay_for_recent_match(self):
        """Match played today should have decay factor of 1.0."""
        from app.services.match_finalization import LeagueMatchService

        decay = LeagueMatchService.calculate_age_decay(self.league, timezone.now())
        self.assertEqual(decay, 1.0)

    def test_half_decay_at_half_life(self):
        """Match at half-life age should have ~0.5 decay."""
        from app.services.match_finalization import LeagueMatchService

        played_at = timezone.now() - timedelta(days=180)
        decay = LeagueMatchService.calculate_age_decay(self.league, played_at)
        self.assertAlmostEqual(decay, 0.5, places=2)

    def test_decay_respects_minimum(self):
        """Very old matches should not decay below minimum."""
        from app.services.match_finalization import LeagueMatchService

        played_at = timezone.now() - timedelta(days=1000)  # Very old
        decay = LeagueMatchService.calculate_age_decay(self.league, played_at)
        self.assertEqual(decay, 0.1)  # Minimum

    def test_decay_disabled(self):
        """Decay factor should be 1.0 when decay is disabled."""
        from app.services.match_finalization import LeagueMatchService

        self.league.age_decay_enabled = False
        self.league.save()

        played_at = timezone.now() - timedelta(days=500)
        decay = LeagueMatchService.calculate_age_decay(self.league, played_at)
        self.assertEqual(decay, 1.0)
