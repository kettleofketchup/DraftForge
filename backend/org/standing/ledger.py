from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from app.models import CustomUser
from events.models import Event
from org.contributions.kinds import REVERSAL_KINDS
from org.membership import resolve_or_create_org_user
from org.models import (
    ContributionEntry,
    ContributionPointValue,
    Organization,
    OrgUser,
    PromoSend,
)
from org.models_promotion_sync import ExternalPromotionReceipt
from org.standing.kinds import KINDS
from org.standing.periods import Period
from org.standing.types import TrackKey


def live_entries() -> Count:
    """Count of rows that are entries.

    A voided point and its void or restore rows add points that net out,
    but no entries.
    """
    return Count("pk", filter=Q(voided=False) & ~Q(kind__in=sorted(REVERSAL_KINDS)))


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


def points_table(org: Organization, kinds: Collection[str]) -> dict[str, int]:
    defaults: dict[str, int] = {}
    for kind in kinds:
        entry = KINDS.get(str(kind))
        if entry is None or entry.default_points is None:
            raise ValueError(f"no default points for kind {str(kind)!r}")
        defaults[str(kind)] = entry.default_points
    overrides = dict(
        ContributionPointValue.objects.nocache()
        .filter(organization=org, kind__in=list(defaults))
        .values_list("kind", "points")
    )
    return {kind: overrides.get(kind, points) for kind, points in defaults.items()}


def in_period(
    qs: QuerySet[ContributionEntry], period: Period
) -> QuerySet[ContributionEntry]:
    if period.start is not None:
        qs = qs.filter(occurred_at__gte=period.start)
    if period.end is not None:
        qs = qs.filter(occurred_at__lt=period.end)
    return qs


def track_entries(org_id: int, *, track: TrackKey) -> QuerySet[ContributionEntry]:
    return ContributionEntry.objects.nocache().filter(
        organization_id=org_id, track=track
    )


def track_rows(track: TrackKey) -> QuerySet[ContributionEntry]:
    return ContributionEntry.objects.nocache().filter(track=track)


def user_rows(
    track: TrackKey, user_pks: Collection[int]
) -> QuerySet[ContributionEntry]:
    return track_rows(track).filter(org_user__user__in=list(user_pks))


def _scoped(
    org_id: int, *, track: TrackKey, period: Period, where: Q | None
) -> QuerySet[ContributionEntry]:
    qs = in_period(track_entries(org_id, track=track), period)
    return qs if where is None else qs.filter(where)


def total(
    org_id: int, *, track: TrackKey, period: Period, where: Q | None = None
) -> int:
    qs = _scoped(org_id, track=track, period=period, where=where)
    return qs.aggregate(total=Sum("points"))["total"] or 0


SortField = Literal["total", "entries"]


def sum_by_member(
    org_id: int,
    *,
    track: TrackKey,
    period: Period,
    sort: SortField = "total",
    where: Q | None = None,
) -> QuerySet[ContributionEntry]:
    return (
        _scoped(org_id, track=track, period=period, where=where)
        .values("org_user")
        .annotate(total=Sum("points"), entries=live_entries())
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
    external_contact: ExternalPromotionReceipt | None = None,
) -> ContributionEntry:
    kind = _check_kind(kind)
    if points is None:
        points = points_for(org, kind)
    org_user = resolve_or_create_org_user(user, org)
    return ContributionEntry.objects.create(
        org_user=org_user,
        organization=org,
        track=KINDS[kind].track,
        kind=kind,
        points=points,
        event=event,
        event_name=event.name if event is not None else "",
        reason=reason,
        awarded_by=awarded_by,
        occurred_at=occurred_at,
        promo_send=promo_send,
        external_contact=external_contact,
    )


def revoke_event_kinds(event: Event, *, kinds: Collection[str]) -> int:
    deleted, _ = (
        ContributionEntry.objects.nocache()
        .filter(
            organization_id=event.organization_id,
            event_id=event.pk,
            kind__in=list(kinds),
            track__in={KINDS[k].track for k in kinds if k in KINDS},
        )
        .delete()
    )
    return deleted


UpsertOutcome = Literal["created", "updated", "deleted", "noop"]

_Existing = tuple[int, int, datetime, str]


def _event_occurred_at(event: Event) -> datetime:
    return event.ends_at or event.scheduled_at


def _check_once_per_event(kind: str) -> str:
    kind = _check_kind(kind)
    if not KINDS[kind].once_per_event:
        raise ValueError(f"kind {kind!r} is not once per event")
    return kind


def _existing_entry(event: Event, org_user: OrgUser, kind: str) -> _Existing | None:
    return (
        ContributionEntry.objects.nocache()
        .filter(event_id=event.pk, org_user_id=org_user.pk, kind=kind)
        .values_list("pk", "points", "occurred_at", "event_name")
        .first()
    )


def _new_event_entry(
    event: Event, org_user_id: int, kind: str, points: int
) -> ContributionEntry:
    return ContributionEntry(
        org_user_id=org_user_id,
        organization_id=event.organization_id,
        track=KINDS[kind].track,
        kind=kind,
        points=points,
        event=event,
        event_name=event.name,
        occurred_at=_event_occurred_at(event),
    )


def upsert_event_entry(
    *, event: Event, org_user: OrgUser, kind: str, points: int | None
) -> UpsertOutcome:
    kind = _check_once_per_event(kind)
    if not points:
        deleted, _ = (
            ContributionEntry.objects.nocache()
            .filter(event_id=event.pk, org_user_id=org_user.pk, kind=kind)
            .delete()
        )
        return "deleted" if deleted else "noop"
    occurred_at = _event_occurred_at(event)
    existing = _existing_entry(event, org_user, kind)
    if existing is None:
        try:
            with transaction.atomic():
                _new_event_entry(event, org_user.pk, kind, points).save()
            return "created"
        except IntegrityError:
            existing = _existing_entry(event, org_user, kind)
            if existing is None:
                raise
    pk, old_points, old_at, old_name = existing
    if (old_points, old_at, old_name) == (points, occurred_at, event.name):
        return "noop"
    ContributionEntry.objects.nocache().filter(pk=pk).update(
        points=points,
        occurred_at=occurred_at,
        event_name=event.name,
        updated_at=timezone.now(),
    )
    return "updated"


@dataclass(frozen=True, slots=True)
class SyncCounts:
    created: int
    updated: int
    deleted: int


def sync_event_kinds(
    event: Event,
    *,
    kinds: Collection[str],
    wanted: Mapping[tuple[int, str], int],
) -> SyncCounts:
    kinds = {_check_once_per_event(kind) for kind in kinds}
    stray = {kind for _, kind in wanted} - kinds
    if stray:
        raise ValueError(f"wanted kinds outside the synced set: {sorted(stray)}")
    want = {key: points for key, points in wanted.items() if points}
    occurred_at = _event_occurred_at(event)
    rows = ContributionEntry.objects.nocache().filter(
        event_id=event.pk, kind__in=sorted(kinds)
    )
    have: set[tuple[int, str]] = set()
    remove: list[int] = []
    refresh: defaultdict[int, list[int]] = defaultdict(list)
    for pk, org_user_id, kind, points, at, name in rows.values_list(
        "pk", "org_user_id", "kind", "points", "occurred_at", "event_name"
    ):
        key = (org_user_id, kind)
        if key not in want or key in have:
            remove.append(pk)
            continue
        have.add(key)
        if (points, at, name) != (want[key], occurred_at, event.name):
            refresh[want[key]].append(pk)
    if remove:
        ContributionEntry.objects.nocache().filter(pk__in=remove).delete()
    now = timezone.now()
    for points, pks in refresh.items():
        ContributionEntry.objects.nocache().filter(pk__in=pks).update(
            points=points,
            occurred_at=occurred_at,
            event_name=event.name,
            updated_at=now,
        )
    create = [
        _new_event_entry(event, org_user_id, kind, points)
        for (org_user_id, kind), points in want.items()
        if (org_user_id, kind) not in have
    ]
    if create:
        ContributionEntry.objects.bulk_create(create)
    return SyncCounts(
        created=len(create),
        updated=sum(len(pks) for pks in refresh.values()),
        deleted=len(remove),
    )
