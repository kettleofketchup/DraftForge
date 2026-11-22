from django.test import SimpleTestCase

from league.models import League
from league.models_rating import LeagueRating
from league.services.rating import (
    EloRatingSystem,
    FixedDeltaRatingSystem,
    get_rating_system,
)


def _rating(player_id: int, base_mmr: int, games_played: int = 10) -> LeagueRating:
    return LeagueRating(
        player_id=player_id, base_mmr=base_mmr, games_played=games_played
    )


class RatingSystemTests(SimpleTestCase):
    def test_get_rating_system_returns_elo_and_fixed_delta(self) -> None:
        self.assertIsInstance(
            get_rating_system(League(rating_system="elo")), EloRatingSystem
        )
        self.assertIsInstance(
            get_rating_system(League(rating_system="fixed_delta")),
            FixedDeltaRatingSystem,
        )
        with self.assertRaisesMessage(ValueError, "Unknown rating system: glicko2"):
            get_rating_system(League(rating_system="glicko2"))

    def test_elo_expected_score_and_delta(self) -> None:
        elo = get_rating_system(League(rating_system="elo"))

        self.assertEqual(
            elo.calculate_team_deltas([_rating(1, 3000)], [_rating(2, 3000)]),
            {
                "winner_delta": 16.0,
                "loser_delta": 16.0,
                "winner_k_factors": {1: 32.0},
                "loser_k_factors": {2: 32.0},
            },
        )
        favourite = elo.calculate_team_deltas([_rating(1, 3400)], [_rating(2, 3000)])
        self.assertAlmostEqual(favourite["winner_delta"], 2.90909090909091)
        self.assertAlmostEqual(favourite["loser_delta"], 2.90909090909091)
        upset = elo.calculate_team_deltas([_rating(1, 3000)], [_rating(2, 3400)])
        self.assertAlmostEqual(upset["winner_delta"], 29.09090909090909)
        self.assertAlmostEqual(upset["loser_delta"], 29.09090909090909)

        placement = elo.calculate_team_deltas(
            [_rating(1, 3000, games_played=0)], [_rating(2, 3000, games_played=0)]
        )
        self.assertEqual(placement["winner_delta"], 32.0)
        self.assertEqual(placement["winner_k_factors"], {1: 64.0})

        decayed = elo.calculate_team_deltas(
            [_rating(1, 3000)], [_rating(2, 3000)], age_decay_factor=0.5
        )
        self.assertEqual(decayed["winner_delta"], 8.0)
        self.assertEqual(decayed["loser_delta"], 8.0)

        with self.assertRaises(ValueError):
            elo.calculate_team_deltas([], [_rating(2, 3000)])

    def test_fixed_delta_win_and_loss(self) -> None:
        fixed = get_rating_system(League(rating_system="fixed_delta"))

        self.assertEqual(
            fixed.calculate_team_deltas(
                [_rating(1, 3000), _rating(3, 2000)], [_rating(2, 5000)]
            ),
            {
                "winner_delta": 25.0,
                "loser_delta": 25.0,
                "winner_k_factors": {1: 25.0, 3: 25.0},
                "loser_k_factors": {2: 25.0},
            },
        )
        decayed = fixed.calculate_team_deltas(
            [_rating(1, 3000)], [_rating(2, 3000)], age_decay_factor=0.5
        )
        self.assertEqual(decayed["winner_delta"], 12.5)
        self.assertEqual(decayed["loser_delta"], 12.5)
