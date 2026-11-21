from collections.abc import Collection
from datetime import datetime
from typing import Literal

from django.db.models import Count, Q, QuerySet, Sum

from app.models import CustomUser, Organization
from events.models import Event
from org.membership import resolve_or_create_org_user
from org.models import ContributionEntry, ContributionPointValue, PromoSend
from org.standing.kinds import KINDS, kinds_for
from org.standing.periods import Period
from org.standing.types import TrackKey


def _check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown ledger kind {kind!r}")
    return kind


def points_for(org: Organization, kind: str) -> int:
    entry = KINDS.get(str(kind))
    if entry is None or entry.default_points is None:
        raise ValueError(f"no default points for kind {str(kind)!r}")
    value = (
        ContributionPointValue.objects.nocache()
        .filter(organization=org, kind=str(kind))
        .values_list("points", flat=True)
        .first()
    )
    return entry.default_points if value is None else value


def in_period(
    qs: QuerySet[ContributionEntry], period: Period
) -> QuerySet[ContributionEntry]:
    if period.start is not None:
        qs = qs.filter(occurred_at__gte=period.start)
    if period.end is not None:
        qs = qs.filter(occurred_at__lt=period.end)
    return qs


def _track_entries(org_id: int, *, track: TrackKey) -> QuerySet[ContributionEntry]:
    return ContributionEntry.objects.nocache().filter(
        organization_id=org_id, kind__in=kinds_for(track)
    )


def total(org_id: int, *, track: TrackKey, period: Period) -> int:
    qs = in_period(_track_entries(org_id, track=track), period)
    return qs.aggregate(total=Sum("points"))["total"] or 0


SortField = Literal["total", "entries"]


def sum_by_member(
    org_id: int, *, track: TrackKey, period: Period, sort: SortField = "total"
) -> QuerySet[ContributionEntry]:
    return (
        in_period(_track_entries(org_id, track=track), period)
        .values("org_user")
        .annotate(total=Sum("points"), entries=Count("pk"))
        .filter(~Q(total=0))
        .order_by(f"-{sort}", "org_user__user__username", "org_user")
    )


def award(
    *,
    org: Organization,
    user: CustomUser,
    kind: str,
    occurred_at: datetime,
    points: int | None = None,
    event: Event | None = None,
    promo_send: PromoSend | None = None,
    reason: str = "",
    awarded_by: CustomUser | None = None,
) -> ContributionEntry:
    kind = _check_kind(kind)
    if points is None:
        points = points_for(org, kind)
    org_user = resolve_or_create_org_user(user, org)
    return ContributionEntry.objects.create(
        org_user=org_user,
        organization=org,
        kind=kind,
        points=points,
        event=event,
        event_name=event.name if event is not None else "",
        reason=reason,
        awarded_by=awarded_by,
        occurred_at=occurred_at,
        promo_send=promo_send,
    )


def revoke_event_kinds(event: Event, *, kinds: Collection[str]) -> int:
    deleted, _ = (
        ContributionEntry.objects.nocache()
        .filter(
            organization_id=event.organization_id,
            event_id=event.pk,
            kind__in=list(kinds),
        )
        .delete()
    )
    return deleted
