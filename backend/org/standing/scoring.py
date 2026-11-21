from collections.abc import Collection, Hashable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

SECONDS_PER_DAY: Final[float] = 86400.0


@dataclass(frozen=True, slots=True)
class RateParams:
    half_life_days: int
    max_age_days: int
    prior: float
    prior_strength: float
    min_count: int


@dataclass(frozen=True, slots=True)
class Observation:
    value: float
    at: datetime


@dataclass(frozen=True, slots=True)
class RateScore:
    rate: float
    status: Literal["new", "scored"]
    count: int
    weight: float


def recency_weight(at: datetime, now: datetime, half_life_days: int) -> float:
    age_days = max(0.0, (now - at).total_seconds() / SECONDS_PER_DAY)
    return 0.5 ** (age_days / half_life_days)


def cutoff(now: datetime, params: RateParams) -> datetime:
    return now - timedelta(days=params.max_age_days)


def _score(
    weighted_sum: float, weight_total: float, count: int, params: RateParams
) -> RateScore:
    alpha = params.prior_strength
    denominator = alpha + weight_total
    if denominator <= 0:
        rate = params.prior
    else:
        rate = (alpha * params.prior + weighted_sum) / denominator
    return RateScore(
        rate=min(1.0, max(0.0, rate)),
        status="new" if count < params.min_count else "scored",
        count=count,
        weight=weight_total,
    )


def weighted_rate(
    obs: Iterable[Observation], *, now: datetime, params: RateParams
) -> RateScore:
    oldest = cutoff(now, params)
    weighted_sum = 0.0
    weight_total = 0.0
    count = 0
    for item in obs:
        if item.at < oldest:
            continue
        weight = recency_weight(item.at, now, params.half_life_days)
        weighted_sum += weight * item.value
        weight_total += weight
        count += 1
    return _score(weighted_sum, weight_total, count, params)


def prior_rate(params: RateParams) -> RateScore:
    return _score(0.0, 0.0, 0, params)


def score_groups[K: Hashable](
    rows: Iterable[tuple[K, float, datetime]],
    *,
    now: datetime,
    params: RateParams,
    fill: Collection[K] | None = None,
) -> dict[K, RateScore]:
    grouped: dict[K, list[Observation]] = {}
    for key, value, at in rows:
        grouped.setdefault(key, []).append(Observation(value=value, at=at))
    scores = {
        key: weighted_rate(obs, now=now, params=params) for key, obs in grouped.items()
    }
    for key in fill or ():
        if key not in scores:
            scores[key] = prior_rate(params)
    return scores


def mean_normalized(values: Iterable[float]) -> float | None:
    items = list(values)
    if not items:
        return None
    return sum(items) / len(items)


def to_score5(rate: float) -> float:
    return 1.0 + 4.0 * rate


def from_score5(score: float) -> float:
    return (score - 1.0) / 4.0
