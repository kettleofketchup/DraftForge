from datetime import datetime
from typing import Any

from django.db.models import Count, Q

from org.contributions.serializers import member_summary
from org.leadership.constants import MIN_EVENT_AGGREGATE_REVIEWS
from org.leadership.kinds import LeadershipKind
from org.leadership.queries import (
    CaptainRating,
    captain_ratings,
    event_trait_averages,
    member_points,
)
from org.leadership.store import effective_traits, get_leadership_settings
from org.models import OrgUser
from org.models_leadership import CaptainTrait, EventCaptain
from org.standing import ledger


def round_score(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def trait_data(trait: CaptainTrait) -> dict[str, Any]:
    return {
        "key": trait.key,
        "label": trait.label,
        "order": trait.order,
        "active": trait.active,
    }


def rating_data(
    rating: CaptainRating | None, traits: list[CaptainTrait]
) -> dict[str, Any]:
    rating = rating or CaptainRating(overall=None)
    return {
        "rating": round_score(rating.overall),
        "status": rating.status,
        "reviews": rating.reviews,
        "traits": [
            {**trait_data(t), "rating": round_score(rating.traits.get(t.pk))}
            for t in traits
            if t.active
        ],
    }


def _history(
    org_user: OrgUser, traits: list[CaptainTrait], *, now: datetime, staff: bool
) -> list[dict[str, Any]]:
    settings = get_leadership_settings(org_user.organization_id)
    snaps = list(
        EventCaptain.objects.nocache()
        .filter(captain=org_user)
        .select_related("event")
        .annotate(live=Count("reviews", filter=Q(reviews__voided_at__isnull=True)))
        .order_by("-event__scheduled_at", "-pk")[:50]
    )
    released = {
        s.pk
        for s in snaps
        if s.voided_at is None
        and s.window_closes_at <= now
        and s.live >= settings.rating_min_reviewers
    }
    visible = [s for s in snaps if staff or s.pk in released]
    shown_avgs = {
        s.pk for s in visible if staff or s.live >= MIN_EVENT_AGGREGATE_REVIEWS
    }
    averages = event_trait_averages(shown_avgs)
    points = dict(
        ledger.track_rows("leadership")
        .filter(
            org_user=org_user,
            kind=LeadershipKind.CAPTAIN_RATING.value,
            event_id__in=[s.event_id for s in visible],
        )
        .values_list("event_id", "points")
    )
    by_pk = {t.pk: t for t in traits}
    rows: list[dict[str, Any]] = []
    for snap in visible:
        row: dict[str, Any] = {
            "event_id": snap.event_id,
            "event_name": snap.event.name,
            "scheduled_at": snap.event.scheduled_at,
            "team_name": snap.team_name,
            "placement": snap.placement,
            "captain_rating_points": points.get(snap.event_id, 0),
            "reviews": snap.live,
            "released": snap.pk in released,
            "traits": (
                [
                    {"key": by_pk[t].key, "label": by_pk[t].label, "average": avg}
                    for t, avg in averages[snap.pk].items()
                    if t in by_pk
                ]
                if snap.pk in shown_avgs
                else None
            ),
        }
        if staff:
            row["window_closes_at"] = snap.window_closes_at
            row["voided"] = snap.voided_at is not None
            row["pool_size"] = snap.teammates.count()
        rows.append(row)
    return rows


def member_payload(
    org_user: OrgUser, *, now: datetime, detail: bool, staff: bool
) -> dict[str, Any]:
    org_id = org_user.organization_id
    settings = get_leadership_settings(org_id)
    traits = effective_traits(org_id)
    rating = captain_ratings(
        org_id, settings, traits, now=now, captain_ids=[org_user.pk]
    ).get(org_user.pk)
    payload: dict[str, Any] = {
        "member": member_summary(org_user),
        **rating_data(rating, traits),
        "points": member_points(org_user, settings, now=now),
    }
    if detail:
        payload["history"] = _history(org_user, traits, now=now, staff=staff)
    return payload
