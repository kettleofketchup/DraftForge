from dataclasses import replace
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from org.standing.scoring import (
    Observation,
    RateParams,
    cutoff,
    from_score5,
    mean_normalized,
    prior_rate,
    recency_weight,
    score_groups,
    to_score5,
    weighted_rate,
)

NOW = datetime(2026, 11, 19, tzinfo=UTC)
P = RateParams(
    half_life_days=90, max_age_days=365, prior=0.85, prior_strength=3.0, min_count=3
)


def _obs(*values: float, age_days: float = 0.0) -> list[Observation]:
    return [Observation(v, NOW - timedelta(days=age_days)) for v in values]


class WeightedRateTest(SimpleTestCase):
    def test_worked_example(self) -> None:
        score = weighted_rate(_obs(1.0, 1.0, 1.0, 0.0), now=NOW, params=P)
        self.assertEqual(round(score.rate, 3), 0.793)
        self.assertEqual(score.status, "scored")
        self.assertEqual(score.count, 4)
        self.assertAlmostEqual(score.weight, 4.0, places=9)

    def test_half_value_counts_half(self) -> None:
        params = replace(P, prior_strength=0.0)
        self.assertEqual(weighted_rate(_obs(0.5), now=NOW, params=params).rate, 0.5)

    def test_prior_when_empty(self) -> None:
        score = weighted_rate([], now=NOW, params=P)
        self.assertEqual((score.rate, score.status, score.count), (0.85, "new", 0))
        self.assertEqual(prior_rate(P), score)

    def test_zero_alpha_empty_returns_prior(self) -> None:
        params = replace(P, prior_strength=0.0)
        self.assertEqual(weighted_rate([], now=NOW, params=params).rate, 0.85)
        self.assertEqual(weighted_rate(_obs(0.0), now=NOW, params=params).rate, 0.0)

    def test_cutoff_drops_old_rows(self) -> None:
        self.assertEqual(cutoff(NOW, P), NOW - timedelta(days=365))
        score = weighted_rate(_obs(0.0, age_days=366), now=NOW, params=P)
        self.assertEqual((score.count, score.rate), (0, 0.85))

    def test_rate_clamped(self) -> None:
        params = replace(P, prior_strength=0.0)
        self.assertEqual(weighted_rate(_obs(1.5), now=NOW, params=params).rate, 1.0)

    def test_min_count_boundary(self) -> None:
        self.assertEqual(weighted_rate(_obs(1, 1), now=NOW, params=P).status, "new")
        self.assertEqual(
            weighted_rate(_obs(1, 1, 1), now=NOW, params=P).status, "scored"
        )


class RecencyWeightTest(SimpleTestCase):
    def test_half_life(self) -> None:
        self.assertAlmostEqual(
            recency_weight(NOW - timedelta(days=90), NOW, 90), 0.5, places=9
        )

    def test_future_clamps_to_one(self) -> None:
        self.assertEqual(recency_weight(NOW + timedelta(days=3), NOW, 90), 1.0)


class ScoreGroupsTest(SimpleTestCase):
    def test_groups_and_fill(self) -> None:
        rows = [("a", 1.0, NOW), ("a", 0.0, NOW), ("b", 1.0, NOW)]
        scores = score_groups(rows, now=NOW, params=P, fill=["a", "c"])
        self.assertEqual(set(scores), {"a", "b", "c"})
        self.assertEqual(scores["a"].count, 2)
        self.assertEqual(scores["c"], prior_rate(P))
        self.assertNotIn("c", score_groups(rows, now=NOW, params=P))


class HelpersTest(SimpleTestCase):
    def test_mean_normalized(self) -> None:
        self.assertIsNone(mean_normalized([]))
        self.assertEqual(mean_normalized([0.0, 1.0]), 0.5)
        self.assertEqual(mean_normalized([0.25, 0.75]), 0.5)

    def test_score5_round_trip(self) -> None:
        self.assertEqual(to_score5(0.0), 1.0)
        self.assertEqual(to_score5(1.0), 5.0)
        self.assertEqual(from_score5(to_score5(0.25)), 0.25)
