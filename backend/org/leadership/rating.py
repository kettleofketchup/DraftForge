from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from events.models import Event
from org.leadership.constants import SCORE_MAX, SCORE_MIN
from org.leadership.kinds import LeadershipKind
from org.leadership.settings import get_leadership_settings
from org.models import ContributionEntry
from org.models_leadership import CaptainTraitScore, EventCaptain
from org.standing import ledger
from telemetry.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RatingUpsert:
    before: int
    after: int
    reviewers: int
    outcome: ledger.UpsertOutcome


def round_half_up(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def review_mean(scores: Iterable[int]) -> Fraction:
    values = list(scores)
    if not values:
        raise ValueError("a review needs at least one score")
    return Fraction(
        sum(s - SCORE_MIN for s in values), (SCORE_MAX - SCORE_MIN) * len(values)
    )


def rating_points(
    review_means: Sequence[Fraction], *, max_points: int, min_reviews: int
) -> int:
    if not review_means or len(review_means) < min_reviews:
        return 0
    return max(0, round_half_up(max_points * sum(review_means) / len(review_means)))


def review_means(snapshot_id: int) -> list[Fraction]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for review_id, score in (
        CaptainTraitScore.objects.nocache()
        .filter(review__event_captain_id=snapshot_id, review__voided_at__isnull=True)
        .values_list("review_id", "score")
    ):
        grouped[review_id].append(score)
    return [review_mean(values) for values in grouped.values()]


def current_points(snapshot: EventCaptain) -> int:
    return (
        ContributionEntry.objects.nocache()
        .filter(
            event_id=snapshot.event_id,
            org_user_id=snapshot.captain_id,
            kind=LeadershipKind.CAPTAIN_RATING.value,
        )
        .values_list("points", flat=True)
        .first()
        or 0
    )


def upsert_captain_rating(
    snapshot: EventCaptain, *, now: datetime, force: bool = False
) -> RatingUpsert | None:
    """Recompute captain_rating for one snapshot. Frozen once the window
    closes unless force (staff moderation). Caller holds the snapshot lock."""
    if not force and now >= snapshot.window_closes_at:
        return None
    event = Event.objects.nocache().get(pk=snapshot.event_id)
    settings = get_leadership_settings(snapshot.organization_id)
    means = review_means(snapshot.pk)
    points = (
        0
        if snapshot.voided_at is not None
        else rating_points(
            means,
            max_points=settings.rating_max_points,
            min_reviews=settings.rating_min_reviewers,
        )
    )
    before = current_points(snapshot)
    outcome = ledger.upsert_event_entry(
        event=event,
        org_user=snapshot.captain,
        kind=LeadershipKind.CAPTAIN_RATING.value,
        points=points or None,
    )
    log.info(
        "captain_rating_upserted",
        system="org",
        subsystem="leadership",
        org_id=snapshot.organization_id,
        event_id=snapshot.event_id,
        captain_org_user_id=snapshot.captain_id,
        points=points,
        reviewers=len(means),
        outcome=outcome,
    )
    return RatingUpsert(
        before=before, after=points, reviewers=len(means), outcome=outcome
    )
