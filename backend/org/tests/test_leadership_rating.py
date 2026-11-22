from fractions import Fraction

from django.test import SimpleTestCase

from org.leadership.constants import SETTINGS_DEFAULTS
from org.leadership.rating import (
    captain_rating_points,
    display,
    overall_rate,
    rate_params,
    review_mean,
    round_half_up,
)
from org.models_leadership import OrgLeadershipSettings


def means(*reviews: list[int]) -> list[Fraction]:
    return [review_mean(r) for r in reviews]


class RatingMathTest(SimpleTestCase):
    def test_review_mean_normalises_to_unit_range(self) -> None:
        self.assertEqual(review_mean([1, 1, 1]), 0)
        self.assertEqual(review_mean([5, 5]), 1)
        self.assertEqual(review_mean([3, 4]), Fraction(5, 8))

    def test_review_mean_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            review_mean([])

    def test_zero_reviews_is_none(self) -> None:
        self.assertIsNone(captain_rating_points([], max_points=10, min_reviewers=2))

    def test_below_min_reviewers_is_none(self) -> None:
        self.assertIsNone(
            captain_rating_points(means([5]), max_points=10, min_reviewers=2)
        )

    def test_all_ones_is_none(self) -> None:
        self.assertIsNone(
            captain_rating_points(means([1], [1]), max_points=10, min_reviewers=2)
        )

    def test_all_fives_is_max(self) -> None:
        self.assertEqual(
            captain_rating_points(means([5], [5]), max_points=10, min_reviewers=2), 10
        )

    def test_mixed_means(self) -> None:
        self.assertEqual(
            captain_rating_points(
                means([3, 4], [4, 4]), max_points=10, min_reviewers=2
            ),
            7,
        )

    def test_half_rounds_up(self) -> None:
        self.assertEqual(round_half_up(Fraction(5, 2)), 3)
        self.assertEqual(round_half_up(Fraction(9, 4)), 2)
        self.assertEqual(
            captain_rating_points([Fraction(1, 4)] * 2, max_points=10, min_reviewers=2),
            3,
        )

    def test_seven_trait_half_rounds_up(self) -> None:
        offsets = [22, 0, 0, 14, 14]
        exact = [Fraction(o, 28) for o in offsets]
        floats = [o / 28 for o in offsets]
        self.assertEqual(round(7 * sum(floats) / len(floats)), 2)
        self.assertEqual(captain_rating_points(exact, max_points=7, min_reviewers=2), 3)

    def test_overall_rate_averages_active_traits_present(self) -> None:
        self.assertEqual(overall_rate({1: 0.5, 2: 1.0, 3: 0.2}, {1, 2}), 0.75)

    def test_overall_rate_empty_is_none(self) -> None:
        self.assertIsNone(overall_rate({}, {1, 2}))
        self.assertIsNone(overall_rate({3: 0.2}, {1, 2}))

    def test_display(self) -> None:
        self.assertIsNone(display(None))
        self.assertEqual(display(0.75), 4.0)
        self.assertEqual(display(1 / 3), 2.33)

    def test_rate_params_defaults(self) -> None:
        params = rate_params(OrgLeadershipSettings())
        self.assertEqual(params.prior, 0.5)
        self.assertEqual(params.min_count, SETTINGS_DEFAULTS["ranked_min_reviews"])
        self.assertEqual(params.half_life_days, SETTINGS_DEFAULTS["half_life_days"])
        self.assertEqual(params.max_age_days, SETTINGS_DEFAULTS["max_age_days"])
        self.assertEqual(params.prior_strength, SETTINGS_DEFAULTS["prior_strength"])
