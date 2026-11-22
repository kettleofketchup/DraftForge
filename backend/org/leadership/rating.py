from collections.abc import Collection, Iterable, Mapping, Sequence
from fractions import Fraction

from org.leadership.constants import SCORE_MAX, SCORE_MIN
from org.models_leadership import OrgLeadershipSettings
from org.standing.scoring import RateParams, from_score5, to_score5


def round_half_up(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def review_mean(scores: Iterable[int]) -> Fraction:
    values = list(scores)
    if not values:
        raise ValueError("a review needs at least one score")
    return Fraction(
        sum(s - SCORE_MIN for s in values), (SCORE_MAX - SCORE_MIN) * len(values)
    )


def captain_rating_points(
    review_means: Sequence[Fraction], *, max_points: int, min_reviewers: int
) -> int | None:
    if not review_means or len(review_means) < min_reviewers:
        return None
    points = round_half_up(max_points * sum(review_means) / len(review_means))
    return points or None


def rate_params(settings: OrgLeadershipSettings) -> RateParams:
    return RateParams(
        half_life_days=settings.half_life_days,
        max_age_days=settings.max_age_days,
        prior=from_score5(float(settings.prior_rating)),
        prior_strength=float(settings.prior_strength),
        min_count=settings.ranked_min_reviews,
    )


def overall_rate(
    trait_rates: Mapping[int, float], active_trait_ids: Collection[int]
) -> float | None:
    present = [rate for key, rate in trait_rates.items() if key in active_trait_ids]
    if not present:
        return None
    return sum(present) / len(present)


def display(rate: float | None) -> float | None:
    if rate is None:
        return None
    return round(to_score5(rate), 2)
