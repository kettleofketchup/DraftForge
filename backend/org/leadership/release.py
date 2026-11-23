from datetime import datetime, timedelta
from typing import Final

from django.db.models import Count, Q, QuerySet

from org.leadership.constants import MIN_RELEASE_REVIEWS, ReleaseState
from org.models_leadership import EventCaptain, OrgLeadershipSettings

LIVE_REVIEWS: Final[Q] = Q(reviews__voided_at__isnull=True)


def release_floor(min_reviewers: int) -> int:
    return max(min_reviewers, MIN_RELEASE_REVIEWS)


def annotate_live(qs: QuerySet[EventCaptain]) -> QuerySet[EventCaptain]:
    return qs.annotate(live=Count("reviews", filter=LIVE_REVIEWS))


def release_q(settings: OrgLeadershipSettings, *, now: datetime) -> Q:
    base = Q(
        voided_at__isnull=True,
        window_closes_at__lte=now,
        live__gte=release_floor(settings.rating_min_reviewers),
    )
    if not settings.require_staff_release:
        return base
    gate = Q(released_at__isnull=False)
    hours = settings.auto_release_after_hours
    if hours is not None:
        gate |= Q(window_closes_at__lte=now - timedelta(hours=hours))
    return base & gate


def released_snapshots(
    org_id: int, *, now: datetime, settings: OrgLeadershipSettings
) -> QuerySet[EventCaptain]:
    return annotate_live(
        EventCaptain.objects.nocache().filter(organization_id=org_id)
    ).filter(release_q(settings, now=now))


def auto_release_at(
    snap: EventCaptain, settings: OrgLeadershipSettings
) -> datetime | None:
    hours = settings.auto_release_after_hours
    if not settings.require_staff_release or hours is None:
        return None
    return snap.window_closes_at + timedelta(hours=hours)


def _gate_passed(
    snap: EventCaptain, settings: OrgLeadershipSettings, now: datetime
) -> bool:
    if not settings.require_staff_release or snap.released_at is not None:
        return True
    auto = auto_release_at(snap, settings)
    return auto is not None and auto <= now


def release_state(
    snap: EventCaptain,
    *,
    live: int,
    settings: OrgLeadershipSettings,
    now: datetime,
) -> ReleaseState:
    if snap.voided_at is not None:
        return "voided"
    if snap.window_closes_at > now:
        return "open"
    if live < release_floor(settings.rating_min_reviewers):
        return "short"
    if not _gate_passed(snap, settings, now):
        return "pending"
    return "released"


def is_released(
    snap: EventCaptain,
    *,
    live: int,
    settings: OrgLeadershipSettings,
    now: datetime,
) -> bool:
    return release_state(snap, live=live, settings=settings, now=now) == "released"
