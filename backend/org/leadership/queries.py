from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict

from django.db.models import Avg, Exists, OuterRef, Q, QuerySet

from org.leadership.constants import MIN_EVENT_AGGREGATE_REVIEWS
from org.leadership.kinds import LeadershipKind
from org.leadership.rating import display, overall_rate, rate_params
from org.leadership.release import (
    annotate_live,
    is_released,
    released_snapshots,
)
from org.leadership.release import (
    release_floor as release_floor,
)
from org.models import ContributionEntry, OrgUser
from org.models_leadership import (
    CaptainTrait,
    CaptainTraitScore,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.standing import ledger
from org.standing.periods import ALL_TIME, Period, month_period, resolve_org_tz
from org.standing.scoring import cutoff, from_score5, score_groups


@dataclass(frozen=True, slots=True)
class CaptainRating:
    org_user_id: int
    overall: float | None
    traits: Mapping[int, float]
    reviews: int
    status: Literal["ranked", "new"]


class EventAggregate(TypedDict):
    event_id: int
    event_name: str
    scheduled_at: datetime
    team_name: str
    placement: int | None
    released: bool
    reviews: int | None
    rating: float | None
    traits: list[dict[str, Any]] | None
    captain_rating_points: int | None


def released_points_q(org_id: int, *, now: datetime) -> Q:
    closed = EventCaptain.objects.nocache().filter(
        organization_id=org_id,
        event=OuterRef("event"),
        captain=OuterRef("org_user"),
        voided_at__isnull=True,
        window_closes_at__lte=now,
    )
    return ~Q(kind=LeadershipKind.CAPTAIN_RATING.value) | Q(Exists(closed))


def rating_board(
    org_id: int,
    *,
    now: datetime,
    settings: OrgLeadershipSettings,
    traits: Sequence[CaptainTrait],
    include_unreleased: bool = False,
    captain_ids: Collection[int] | None = None,
) -> dict[int, CaptainRating]:
    params = rate_params(settings)
    rows = CaptainTraitScore.objects.nocache().filter(
        review__voided_at__isnull=True,
        review__event_captain__organization_id=org_id,
        review__event_captain__voided_at__isnull=True,
        review__event_captain__event__scheduled_at__gte=cutoff(now, params),
    )
    if not include_unreleased:
        released = released_snapshots(org_id, now=now, settings=settings)
        rows = rows.filter(review__event_captain__in=released.values("pk"))
    if captain_ids is not None:
        rows = rows.filter(review__event_captain__captain_id__in=list(captain_ids))
    reviews: defaultdict[int, set[int]] = defaultdict(set)
    observations: list[tuple[tuple[int, int], float, datetime]] = []
    for captain, trait, review, score, at in rows.values_list(
        "review__event_captain__captain_id",
        "trait_id",
        "review_id",
        "score",
        "review__event_captain__event__scheduled_at",
    ):
        reviews[captain].add(review)
        observations.append(((captain, trait), from_score5(score), at))
    groups = score_groups(observations, now=now, params=params)
    active = {t.pk for t in traits if t.active and t.pk is not None}
    per_captain: defaultdict[int, dict[int, float]] = defaultdict(dict)
    for (captain, trait), scored in groups.items():
        if trait in active:
            per_captain[captain][trait] = scored.rate
    result: dict[int, CaptainRating] = {}
    for captain, review_ids in reviews.items():
        trait_rates = per_captain.get(captain, {})
        count = len(review_ids)
        result[captain] = CaptainRating(
            org_user_id=captain,
            overall=overall_rate(trait_rates, active),
            traits=trait_rates,
            reviews=count,
            status="ranked" if count >= settings.ranked_min_reviews else "new",
        )
    return result


def points_board(
    org_id: int, period: Period, *, now: datetime, include_unreleased: bool = False
) -> QuerySet[ContributionEntry]:
    return ledger.sum_by_member(
        org_id,
        track="leadership",
        period=period,
        where=None if include_unreleased else released_points_q(org_id, now=now),
    )


def member_points(
    org_user: OrgUser, *, now: datetime, include_unreleased: bool
) -> dict[str, int]:
    org_id = org_user.organization_id
    tz = resolve_org_tz(org_user.organization)
    local_now = now.astimezone(tz)
    where = Q(org_user=org_user)
    if not include_unreleased:
        where &= released_points_q(org_id, now=now)
    all_time = Period(start=None, end=None, label=ALL_TIME)
    this_month = month_period(tz, local_now.year, local_now.month)
    return {
        "all_time": ledger.total(
            org_id, track="leadership", period=all_time, where=where
        ),
        "this_month": ledger.total(
            org_id, track="leadership", period=this_month, where=where
        ),
    }


def _trait_averages(snapshot_ids: Collection[int]) -> dict[int, dict[int, float]]:
    found: defaultdict[int, dict[int, float]] = defaultdict(dict)
    if not snapshot_ids:
        return found
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
        found[snap][trait] = float(avg)
    return found


def captain_events(
    org_user: OrgUser,
    *,
    now: datetime,
    settings: OrgLeadershipSettings,
    traits: Sequence[CaptainTrait],
    staff: bool,
) -> list[EventAggregate]:
    snaps = list(
        annotate_live(EventCaptain.objects.nocache().filter(captain=org_user))
        .select_related("event")
        .order_by("-event__scheduled_at", "-pk")
    )
    released = {
        s.pk for s in snaps if is_released(s, live=s.live, settings=settings, now=now)
    }
    visible = [s for s in snaps if staff or s.pk in released]
    shown = {s.pk for s in visible if staff or s.live >= MIN_EVENT_AGGREGATE_REVIEWS}
    averages = _trait_averages(shown)
    points = (
        dict(
            ledger.track_rows("leadership")
            .filter(
                org_user=org_user,
                kind=LeadershipKind.CAPTAIN_RATING.value,
                event_id__in=[s.event_id for s in visible],
            )
            .values_list("event_id", "points")
        )
        if visible
        else {}
    )
    active = [t for t in traits if t.active and t.pk is not None]
    rows: list[EventAggregate] = []
    for snap in visible:
        show = snap.pk in shown
        trait_avgs = averages.get(snap.pk, {})
        listed = [t for t in active if t.pk in trait_avgs]
        overall = overall_rate(
            {t.pk: from_score5(trait_avgs[t.pk]) for t in listed},
            {t.pk for t in listed},
        )
        rows.append(
            EventAggregate(
                event_id=snap.event_id,
                event_name=snap.event.name,
                scheduled_at=snap.event.scheduled_at,
                team_name=snap.team_name,
                placement=snap.placement,
                released=snap.pk in released,
                reviews=snap.live if show else None,
                rating=display(overall) if show else None,
                traits=(
                    [
                        {
                            "key": t.key,
                            "label": t.label,
                            "average": round(trait_avgs[t.pk], 2),
                        }
                        for t in listed
                    ]
                    if show
                    else None
                ),
                captain_rating_points=points.get(snap.event_id),
            )
        )
    return rows
