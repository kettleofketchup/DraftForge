from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import sqrt

from django.test import SimpleTestCase

from org.conduct.constants import Outcome
from org.conduct.params import late_cancel_weight, rate_params
from org.conduct.scoring import (
    MemberScore,
    forecast,
    member_score,
    prior_member_score,
    show_value,
)
from org.models_conduct import OrgConductSettings
from org.standing.scoring import RateParams, score_groups

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def _settings(**overrides: object) -> OrgConductSettings:
    fields: dict[str, object] = {
        "half_life_days": 90,
        "max_age_days": 365,
        "prior_show_rate": Decimal("0.85"),
        "prior_strength": Decimal("3.0"),
        "min_events": 3,
        "late_cancel_weight": Decimal("0.5"),
    }
    fields.update(overrides)
    return OrgConductSettings(**fields)


def _score(
    settings: OrgConductSettings, *outcomes: str, age_days: float = 0.0
) -> MemberScore:
    weight = late_cancel_weight(settings)
    at = NOW - timedelta(days=age_days)
    rows = [
        (1, value, at)
        for value in (show_value(o, weight) for o in outcomes)
        if value is not None
    ]
    scores = score_groups(rows, now=NOW, params=rate_params(settings), fill=[1])
    return member_score(scores[1])


class ParamsTest(SimpleTestCase):
    def test_rate_params_mapping(self) -> None:
        self.assertEqual(
            rate_params(_settings()),
            RateParams(
                half_life_days=90,
                max_age_days=365,
                prior=0.85,
                prior_strength=3.0,
                min_count=3,
            ),
        )

    def test_late_cancel_weight_is_float(self) -> None:
        weight = late_cancel_weight(_settings(late_cancel_weight=Decimal("0.25")))
        self.assertIsInstance(weight, float)
        self.assertEqual(weight, 0.25)


class MemberScoreTest(SimpleTestCase):
    def test_worked_example(self) -> None:
        score = _score(
            _settings(),
            Outcome.ATTENDED,
            Outcome.ATTENDED,
            Outcome.ATTENDED,
            Outcome.NO_SHOW,
        )
        self.assertEqual(round(score.show_rate, 3), 0.793)
        self.assertEqual(score.status, "scored")
        self.assertEqual(score.counted_events, 4)
        self.assertAlmostEqual(score.weighted_events, 4.0, places=9)

    def test_new_member_prior(self) -> None:
        settings = _settings()
        score = _score(settings)
        self.assertEqual(score.show_rate, 0.85)
        self.assertEqual(score.status, "new")
        self.assertEqual(score.counted_events, 0)
        self.assertEqual(prior_member_score(settings), score)

    def test_alpha_zero_no_data_returns_prior(self) -> None:
        settings = _settings(prior_strength=Decimal("0"))
        self.assertEqual(_score(settings).show_rate, 0.85)
        self.assertEqual(prior_member_score(settings).show_rate, 0.85)

    def test_alpha_zero_all_no_show_is_zero(self) -> None:
        settings = _settings(prior_strength=Decimal("0"))
        self.assertEqual(_score(settings, Outcome.NO_SHOW).show_rate, 0.0)

    def test_excused_and_pending_excluded(self) -> None:
        settings = _settings()
        before = _score(settings, Outcome.ATTENDED, Outcome.NO_SHOW)
        after = _score(
            settings,
            Outcome.ATTENDED,
            Outcome.NO_SHOW,
            Outcome.EXCUSED,
            Outcome.PENDING,
        )
        self.assertEqual(after, before)

    def test_late_cancel_weight(self) -> None:
        half = _settings(prior_strength=Decimal("0"))
        self.assertEqual(_score(half, Outcome.LATE_CANCEL).show_rate, 0.5)
        full = _settings(prior_strength=Decimal("0"), late_cancel_weight=Decimal("1"))
        self.assertEqual(_score(full, Outcome.LATE_CANCEL).show_rate, 0.0)

    def test_max_age_cutoff(self) -> None:
        score = _score(_settings(), Outcome.NO_SHOW, age_days=366)
        self.assertEqual(score.counted_events, 0)
        self.assertEqual(score.show_rate, 0.85)

    def test_new_scored_boundary(self) -> None:
        settings = _settings()
        two = _score(settings, Outcome.ATTENDED, Outcome.ATTENDED)
        three = _score(settings, Outcome.ATTENDED, Outcome.ATTENDED, Outcome.ATTENDED)
        self.assertEqual(two.status, "new")
        self.assertEqual(three.status, "scored")

    def test_future_start_weighs_one(self) -> None:
        score = _score(_settings(), Outcome.NO_SHOW, age_days=-3)
        self.assertAlmostEqual(score.weighted_events, 1.0, places=9)


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
