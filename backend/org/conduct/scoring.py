import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from org.conduct.constants import Outcome
from org.conduct.params import ConductParams
from org.standing.scoring import Observation, RateScore, prior_rate, weighted_rate

Z_80: Final[float] = 1.2816


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


def show_value(outcome: str, late_cancel_weight: float) -> float | None:
    if outcome == Outcome.ATTENDED:
        return 1.0
    if outcome == Outcome.NO_SHOW:
        return 0.0
    if outcome == Outcome.LATE_CANCEL:
        return 1.0 - late_cancel_weight
    return None


def member_score(score: RateScore) -> MemberScore:
    return MemberScore(
        show_rate=score.rate,
        status=score.status,
        counted_events=score.count,
        weighted_events=score.weight,
    )


def observations(
    points: Iterable[OutcomePoint], late_cancel_weight: float
) -> list[Observation]:
    found: list[Observation] = []
    for point in points:
        value = show_value(point.outcome, late_cancel_weight)
        if value is not None:
            found.append(Observation(value=value, at=point.event_starts_at))
    return found


def score_member(
    points: Iterable[OutcomePoint], *, now: datetime, params: ConductParams
) -> MemberScore:
    obs = observations(points, params.late_cancel_weight)
    return member_score(weighted_rate(obs, now=now, params=params.rate))


def prior_score(params: ConductParams) -> MemberScore:
    return member_score(prior_rate(params.rate))


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
