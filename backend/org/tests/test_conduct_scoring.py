from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import sqrt

from django.test import SimpleTestCase

from org.conduct.constants import Outcome
from org.conduct.scoring import (
    OutcomePoint,
    ScoreParams,
    forecast,
    prior_score,
    recency_weight,
    score_member,
    show_value,
)

NOW = datetime(2026, 11, 19, tzinfo=UTC)
P = ScoreParams(0.5, 90, 365, 0.85, 3.0, 3)


def _points(*outcomes: str, age_days: float = 0.0) -> list[OutcomePoint]:
    return [OutcomePoint(o, NOW - timedelta(days=age_days)) for o in outcomes]


class ScoreMemberTest(SimpleTestCase):
    def test_worked_example(self) -> None:
        points = _points(
            Outcome.ATTENDED, Outcome.ATTENDED, Outcome.ATTENDED, Outcome.NO_SHOW
        )
        score = score_member(points, now=NOW, params=P)
        self.assertEqual(round(score.show_rate, 3), 0.793)
        self.assertEqual(score.status, "scored")
        self.assertEqual(score.counted_events, 4)
        self.assertAlmostEqual(score.weighted_events, 4.0, places=9)

    def test_new_member_prior(self) -> None:
        score = score_member([], now=NOW, params=P)
        self.assertEqual(score.show_rate, 0.85)
        self.assertEqual(score.status, "new")
        self.assertEqual(score.counted_events, 0)
        self.assertEqual(prior_score(P), score)

    def test_alpha_zero_no_data_returns_prior(self) -> None:
        params = replace(P, prior_strength=0.0)
        self.assertEqual(score_member([], now=NOW, params=params).show_rate, 0.85)

    def test_alpha_zero_all_no_show_is_zero(self) -> None:
        params = replace(P, prior_strength=0.0)
        score = score_member(_points(Outcome.NO_SHOW), now=NOW, params=params)
        self.assertEqual(score.show_rate, 0.0)

    def test_excused_and_pending_excluded(self) -> None:
        base = _points(Outcome.ATTENDED, Outcome.NO_SHOW)
        extra = base + _points(Outcome.EXCUSED, Outcome.PENDING)
        before = score_member(base, now=NOW, params=P)
        after = score_member(extra, now=NOW, params=P)
        self.assertEqual(after.show_rate, before.show_rate)
        self.assertEqual(after.counted_events, before.counted_events)

    def test_late_cancel_weight(self) -> None:
        params = replace(P, prior_strength=0.0)
        points = _points(Outcome.LATE_CANCEL)
        self.assertEqual(score_member(points, now=NOW, params=params).show_rate, 0.5)
        full = replace(params, late_cancel_weight=1.0)
        self.assertEqual(score_member(points, now=NOW, params=full).show_rate, 0.0)

    def test_max_age_cutoff(self) -> None:
        score = score_member(_points(Outcome.NO_SHOW, age_days=366), now=NOW, params=P)
        self.assertEqual(score.counted_events, 0)
        self.assertEqual(score.show_rate, 0.85)

    def test_new_scored_boundary(self) -> None:
        two = score_member(
            _points(Outcome.ATTENDED, Outcome.ATTENDED), now=NOW, params=P
        )
        three = score_member(
            _points(Outcome.ATTENDED, Outcome.ATTENDED, Outcome.ATTENDED),
            now=NOW,
            params=P,
        )
        self.assertEqual(two.status, "new")
        self.assertEqual(three.status, "scored")


class RecencyWeightTest(SimpleTestCase):
    def test_half_life_decay(self) -> None:
        self.assertAlmostEqual(
            recency_weight(NOW - timedelta(days=90), NOW, 90), 0.5, places=9
        )

    def test_future_start_weight_is_one(self) -> None:
        self.assertEqual(recency_weight(NOW + timedelta(days=3), NOW, 90), 1.0)


class ShowValueTest(SimpleTestCase):
    def test_values(self) -> None:
        self.assertEqual(show_value(Outcome.ATTENDED, 0.5), 1.0)
        self.assertEqual(show_value(Outcome.NO_SHOW, 0.5), 0.0)
        self.assertEqual(show_value(Outcome.LATE_CANCEL, 0.25), 0.75)
        self.assertIsNone(show_value(Outcome.EXCUSED, 0.5))
        self.assertIsNone(show_value(Outcome.PENDING, 0.5))


class ForecastTest(SimpleTestCase):
    def test_forecast_interval_and_clip(self) -> None:
        result = forecast([0.85] * 30)
        self.assertEqual(result.seat_holders, 30)
        self.assertEqual(round(result.expected), 26)
        spread = 1.2816 * sqrt(30 * 0.85 * 0.15)
        self.assertEqual(result.low, round(25.5 - spread))
        self.assertEqual(result.high, round(25.5 + spread))

        certain = forecast([1.0, 1.0])
        self.assertEqual((certain.low, certain.high), (2, 2))

        empty = forecast([])
        self.assertEqual(
            (empty.seat_holders, empty.expected, empty.low, empty.high), (0, 0.0, 0, 0)
        )

    def test_forecast_clips_to_bounds(self) -> None:
        result = forecast([0.05])
        self.assertEqual(result.low, 0)
        self.assertLessEqual(result.high, 1)
