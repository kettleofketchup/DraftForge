from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from django.db.models import Avg, Count, Exists, OuterRef, Q, QuerySet, Sum

from org.leadership.kinds import LeadershipKind
from org.leadership.store import rate_params
from org.models import ContributionEntry, OrgUser
from org.models_leadership import (
    CaptainReview,
    CaptainTrait,
    CaptainTraitScore,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.standing import ledger
from org.standing.periods import Period
from org.standing.scoring import (
    RateScore,
    cutoff,
    mean_normalized,
    score_groups,
    to_score5,
)


@dataclass(frozen=True, slots=True)
class CaptainRating:
    overall: float | None
    traits: dict[int, float] = field(default_factory=dict)
    reviews: int = 0
    status: Literal["ranked", "new"] = "new"


def _live_reviews() -> Q:
    return Q(reviews__voided_at__isnull=True)


def released_snapshots(
    org_id: int, settings: OrgLeadershipSettings, *, now: datetime
) -> QuerySet[EventCaptain]:
    return (
        EventCaptain.objects.nocache()
        .filter(
            organization_id=org_id, voided_at__isnull=True, window_closes_at__lte=now
        )
        .annotate(live=Count("reviews", filter=_live_reviews()))
        .filter(live__gte=settings.rating_min_reviewers)
    )


def captain_ratings(
    org_id: int,
    settings: OrgLeadershipSettings,
    traits: Collection[CaptainTrait],
    *,
    now: datetime,
    captain_ids: Collection[int] | None = None,
) -> dict[int, CaptainRating]:
    params = rate_params(settings)
    oldest = cutoff(now, params)
    released = released_snapshots(org_id, settings, now=now).filter(
        event__scheduled_at__gte=oldest
    )
    if captain_ids is not None:
        released = released.filter(captain_id__in=list(captain_ids))
    released_ids = released.values("pk")
    rows = (
        CaptainTraitScore.objects.nocache()
        .filter(
            review__event_captain__in=released_ids,
            review__voided_at__isnull=True,
        )
        .values_list(
            "review__event_captain__captain_id",
            "trait_id",
            "score",
            "review__event_captain__event__scheduled_at",
        )
    )
    scores = score_groups(
        (((captain, trait), (score - 1) / 4, at) for captain, trait, score, at in rows),
        now=now,
        params=params,
    )
    counts = dict(
        CaptainReview.objects.nocache()
        .filter(event_captain__in=released_ids, voided_at__isnull=True)
        .values("event_captain__captain_id")
        .annotate(n=Count("pk"))
        .values_list("event_captain__captain_id", "n")
    )
    active = {t.pk for t in traits if t.active and t.pk is not None}
    per_captain: dict[int, dict[int, RateScore]] = defaultdict(dict)
    for (captain, trait), score in scores.items():
        per_captain[captain][trait] = score
    result: dict[int, CaptainRating] = {}
    for captain, by_trait in per_captain.items():
        counted = {t: s for t, s in by_trait.items() if t in active}
        overall = mean_normalized(s.rate for s in counted.values())
        reviews = counts.get(captain, 0)
        result[captain] = CaptainRating(
            overall=to_score5(overall) if overall is not None else None,
            traits={t: to_score5(s.rate) for t, s in counted.items()},
            reviews=reviews,
            status="ranked" if reviews >= settings.ranked_min_reviews else "new",
        )
    return result


def released_points(
    org_id: int, settings: OrgLeadershipSettings, *, now: datetime
) -> QuerySet[ContributionEntry]:
    released = released_snapshots(org_id, settings, now=now).filter(
        event_id=OuterRef("event_id"), captain_id=OuterRef("org_user_id")
    )
    return (
        ledger.track_rows("leadership")
        .filter(organization_id=org_id)
        .filter(~Q(kind=LeadershipKind.CAPTAIN_RATING.value) | Q(Exists(released)))
    )


def points_by_member(
    org_id: int, settings: OrgLeadershipSettings, period: Period, *, now: datetime
) -> QuerySet[ContributionEntry]:
    return (
        ledger.in_period(released_points(org_id, settings, now=now), period)
        .values("org_user")
        .annotate(total=Sum("points"), entries=Count("pk"))
        .filter(~Q(total=0))
        .order_by("-total", "org_user__user__username", "org_user")
    )


def member_points(
    org_user: OrgUser, settings: OrgLeadershipSettings, *, now: datetime
) -> int:
    return (
        released_points(org_user.organization_id, settings, now=now)
        .filter(org_user=org_user)
        .aggregate(total=Sum("points"))["total"]
        or 0
    )


def event_trait_averages(snapshot_ids: Collection[int]) -> dict[int, dict[int, float]]:
    found: dict[int, dict[int, float]] = defaultdict(dict)
    for snap, trait, avg in (
        CaptainTraitScore.objects.nocache()
        .filter(
            review__event_captain_id__in=list(snapshot_ids),
            review__voided_at__isnull=True,
        )
        .values("review__event_captain_id", "trait_id")
        .annotate(avg=Avg("score"))
        .values_list("review__event_captain_id", "trait_id", "avg")
    ):
        found[snap][trait] = round(float(avg), 2)
    return found
