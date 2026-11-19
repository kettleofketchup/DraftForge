import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, Self

from org.conduct.constants import Outcome
from org.models_conduct import OrgConductSettings

Z_80: Final[float] = 1.2816
SECONDS_PER_DAY: Final[float] = 86400.0


@dataclass(frozen=True)
class ScoreParams:
    late_cancel_weight: float
    half_life_days: int
    max_age_days: int
    prior_show_rate: float
    prior_strength: float
    min_events: int

    @classmethod
    def from_settings(cls, s: OrgConductSettings) -> Self:
        return cls(
            late_cancel_weight=float(s.late_cancel_weight),
            half_life_days=s.half_life_days,
            max_age_days=s.max_age_days,
            prior_show_rate=float(s.prior_show_rate),
            prior_strength=float(s.prior_strength),
            min_events=s.min_events,
        )


@dataclass(frozen=True)
class OutcomePoint:
    outcome: str
    event_starts_at: datetime


@dataclass(frozen=True)
class MemberScore:
    show_rate: float
    status: Literal["new", "scored"]
    counted_events: int
    weighted_events: float


@dataclass(frozen=True)
class Forecast:
    seat_holders: int
    expected: float
    low: int
    high: int


def recency_weight(
    event_starts_at: datetime, now: datetime, half_life_days: int
) -> float:
    age_days = max(0.0, (now - event_starts_at).total_seconds() / SECONDS_PER_DAY)
    return 0.5 ** (age_days / half_life_days)


def show_value(outcome: str, late_cancel_weight: float) -> float | None:
    if outcome == Outcome.ATTENDED:
        return 1.0
    if outcome == Outcome.NO_SHOW:
        return 0.0
    if outcome == Outcome.LATE_CANCEL:
        return 1.0 - late_cancel_weight
    return None


def score_member(
    points: Iterable[OutcomePoint], *, now: datetime, params: ScoreParams
) -> MemberScore:
    cutoff = now - timedelta(days=params.max_age_days)
    weighted_sum = 0.0
    weight_total = 0.0
    counted = 0
    for point in points:
        if point.event_starts_at < cutoff:
            continue
        value = show_value(point.outcome, params.late_cancel_weight)
        if value is None:
            continue
        weight = recency_weight(point.event_starts_at, now, params.half_life_days)
        weighted_sum += weight * value
        weight_total += weight
        counted += 1

    alpha = params.prior_strength
    denominator = alpha + weight_total
    if denominator <= 0:
        rate = params.prior_show_rate
    else:
        rate = (alpha * params.prior_show_rate + weighted_sum) / denominator
    return MemberScore(
        show_rate=min(1.0, max(0.0, rate)),
        status="new" if counted < params.min_events else "scored",
        counted_events=counted,
        weighted_events=weight_total,
    )


def prior_score(params: ScoreParams) -> MemberScore:
    return score_member([], now=datetime.max, params=params)


def forecast(probabilities: Sequence[float]) -> Forecast:
    seat_holders = len(probabilities)
    expected = math.fsum(probabilities)
    spread = Z_80 * math.sqrt(math.fsum(p * (1.0 - p) for p in probabilities))
    return Forecast(
        seat_holders=seat_holders,
        expected=expected,
        low=min(seat_holders, max(0, round(expected - spread))),
        high=min(seat_holders, max(0, round(expected + spread))),
    )
