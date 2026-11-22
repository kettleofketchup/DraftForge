from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Avg

from events.models import Event
from org.leadership.kinds import LeadershipKind
from org.leadership.store import get_leadership_settings
from org.models import ContributionEntry
from org.models_leadership import CaptainReview, CaptainTraitScore, EventCaptain
from org.standing import ledger
from org.standing.scoring import from_score5, mean_normalized
from telemetry.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RatingUpsert:
    before: int
    after: int
    reviewers: int
    outcome: ledger.UpsertOutcome


def round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rating_points(
    review_means: list[float], *, max_points: int, min_reviews: int
) -> int:
    if len(review_means) < min_reviews:
        return 0
    mean = mean_normalized(from_score5(m) for m in review_means)
    if mean is None:
        return 0
    return max(0, round_half_up(max_points * mean))


def review_means(snapshot_id: int) -> list[float]:
    live = CaptainReview.objects.nocache().filter(
        event_captain_id=snapshot_id, voided_at__isnull=True
    )
    return [
        float(row["mean"])
        for row in CaptainTraitScore.objects.nocache()
        .filter(review__in=live)
        .values("review_id")
        .annotate(mean=Avg("score"))
        if row["mean"] is not None
    ]


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
