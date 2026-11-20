from collections.abc import Collection
from datetime import datetime
from typing import Literal

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from app.models import CustomUser, Organization
from events.models import Event
from org.membership import resolve_or_create_org_user
from org.models import ContributionEntry, OrgUser, PromoSend
from org.standing.kinds import KINDS, kinds_for
from org.standing.periods import Period
from org.standing.types import TrackKey


def _check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown ledger kind {kind!r}")
    return kind


def in_period(
    qs: QuerySet[ContributionEntry], period: Period
) -> QuerySet[ContributionEntry]:
    if period.start is not None:
        qs = qs.filter(occurred_at__gte=period.start)
    if period.end is not None:
        qs = qs.filter(occurred_at__lt=period.end)
    return qs


def total(qs: QuerySet[ContributionEntry]) -> int:
    return qs.aggregate(total=Sum("points"))["total"] or 0


def track_entries(org_id: int, *, track: TrackKey) -> QuerySet[ContributionEntry]:
    return ContributionEntry.objects.nocache().filter(
        organization_id=org_id, kind__in=kinds_for(track)
    )


def org_total(org_id: int, *, track: TrackKey, period: Period) -> int:
    return total(in_period(track_entries(org_id, track=track), period))


def sum_by_member(
    org_id: int, *, track: TrackKey, period: Period
) -> QuerySet[ContributionEntry]:
    return (
        in_period(track_entries(org_id, track=track), period)
        .values("org_user")
        .annotate(total=Sum("points"), entries=Count("pk"))
        .filter(~Q(total=0))
        .order_by("-total", "org_user__user__username", "org_user")
    )


def award(
    *,
    org: Organization,
    user: CustomUser,
    kind: str,
    occurred_at: datetime,
    points: int,
    event: Event | None = None,
    promo_send: PromoSend | None = None,
    reason: str = "",
    awarded_by: CustomUser | None = None,
) -> ContributionEntry:
    kind = _check_kind(kind)
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


def upsert_event_entry(
    *, event: Event, org_user: OrgUser, kind: str, points: int | None
) -> Literal["created", "updated", "deleted", "noop"]:
    kind = _check_kind(kind)
    rows = ContributionEntry.objects.nocache().filter(
        event=event, org_user=org_user, kind=kind
    )
    if not points:
        deleted, _ = rows.delete()
        return "deleted" if deleted else "noop"
    occurred_at = event.ends_at or event.scheduled_at
    existing = rows.first()
    if existing is None:
        ContributionEntry.objects.create(
            org_user=org_user,
            organization_id=event.organization_id,
            kind=kind,
            points=points,
            event=event,
            event_name=event.name,
            occurred_at=occurred_at,
        )
        return "created"
    if existing.points == points:
        return "noop"
    rows.update(points=points, updated_at=timezone.now())
    return "updated"


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
