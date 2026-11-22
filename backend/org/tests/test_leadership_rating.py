from fractions import Fraction

from django.test import SimpleTestCase

from org.leadership.rating import rating_points, review_mean, round_half_up


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

    def test_below_min_reviewers_is_zero(self) -> None:
        self.assertEqual(rating_points([], max_points=10, min_reviews=2), 0)
        self.assertEqual(rating_points(means([5]), max_points=10, min_reviews=2), 0)

    def test_formula(self) -> None:
        self.assertEqual(
            rating_points(means([1], [1]), max_points=10, min_reviews=2), 0
        )
        self.assertEqual(
            rating_points(means([5], [5]), max_points=10, min_reviews=2), 10
        )
        self.assertEqual(
            rating_points(means([4], [5]), max_points=10, min_reviews=2), 9
        )
        self.assertEqual(
            rating_points(means([3], [2]), max_points=10, min_reviews=2), 4
        )

    def test_half_rounds_up(self) -> None:
        self.assertEqual(round_half_up(Fraction(5, 2)), 3)
        self.assertEqual(round_half_up(Fraction(9, 4)), 2)
        self.assertEqual(
            rating_points([Fraction(1, 4)] * 2, max_points=10, min_reviews=2), 3
        )

    def test_seven_trait_half_rounds_up_exactly(self) -> None:
        offsets = [22, 0, 0, 14, 14]
        exact = [Fraction(o, 28) for o in offsets]
        self.assertEqual(rating_points(exact, max_points=7, min_reviews=2), 3)
