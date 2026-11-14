from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Final, TypeGuard

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Organization, OrgLog
from app.permissions_org import is_org_role_holder
from events.constants import EventState
from events.models import Event
from events.services import resolve_or_create_org_user
from org.contributions.kinds import (
    DEFAULT_POINTS,
    EVENT_STAFF_KINDS,
    RATED_KINDS,
    ContributionKind,
)
from org.contributions.periods import local_day_start_utc, local_noon_utc
from org.contributions.points import points_for
from org.models import (
    ContributionEntry,
    ContributionPointValue,
    OrgFeature,
    OrgUser,
    PromoTemplate,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

MANUAL_MIN_POINTS: Final = 1
MANUAL_MAX_POINTS: Final = 1000
REASON_MAX_LENGTH: Final = 500
POINT_VALUE_MAX: Final = 1000


class _Unset(Enum):
    UNSET = "unset"


UNSET: Final = _Unset.UNSET


@dataclass(frozen=True)
class RescoreResult:
    old: int
    new: int
    changed: int


@dataclass(frozen=True)
class SyncResult:
    created: int
    deleted: int
    updated: int


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_manual_points(points: object) -> int:
    if _is_int(points) and MANUAL_MIN_POINTS <= points <= MANUAL_MAX_POINTS:
        return points
    raise ValueError(
        f"points must be an integer from {MANUAL_MIN_POINTS} to {MANUAL_MAX_POINTS}"
    )


def _check_reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if not cleaned:
        raise ValueError("reason is required")
    if len(cleaned) > REASON_MAX_LENGTH:
        raise ValueError(f"reason must be at most {REASON_MAX_LENGTH} characters")
    return cleaned


def _check_event(org: Organization, event: Event | None) -> None:
    if event is not None and event.organization_id != org.pk:
        raise ValueError("event does not belong to this organization")


def _manual_snapshot(entry: ContributionEntry) -> dict[str, Any]:
    return {
        "points": entry.points,
        "reason": entry.reason,
        "occurred_at": entry.occurred_at.isoformat(),
        "event_id": entry.event_id,
    }


def _require_manual(entry: ContributionEntry) -> None:
    if entry.kind != ContributionKind.MANUAL:
        raise ValueError("only manual awards can be edited or deleted")


@transaction.atomic
def award_entry(
    *,
    org: Organization,
    user: CustomUser,
    kind: str,
    occurred_at: datetime,
    event: Event | None = None,
    awarded_by: CustomUser | None = None,
    reason: str = "",
    points: int | None = None,
) -> ContributionEntry:
    kind = ContributionKind(kind).value
    _check_event(org, event)
    if points is None:
        points = points_for(org, kind)
    org_user = resolve_or_create_org_user(user, org)
    entry = ContributionEntry.objects.create(
        org_user=org_user,
        organization=org,
        kind=kind,
        points=points,
        event=event,
        event_name=event.name if event is not None else "",
        reason=reason,
        awarded_by=awarded_by,
        occurred_at=occurred_at,
    )
    log.info(
        "contribution_awarded",
        system="org",
        subsystem="contributions",
        org_id=org.pk,
        user_id=user.pk,
        entry_id=entry.pk,
        kind=kind,
        points=points,
        event_id=event.pk if event is not None else None,
        awarded_by_id=awarded_by.pk if awarded_by is not None else None,
    )
    return entry


def should_sync_staff(event: Event) -> bool:
    return (
        event.state == EventState.COMPLETED
        or event.contributions_awarded_at is not None
    )


@transaction.atomic
def sync_event_staff_entries(event: Event) -> SyncResult:
    org = event.organization
    occurred_at = event.ends_at or event.scheduled_at
    wanted: dict[tuple[int, str], CustomUser] = {}
    if event.host_id is not None:
        host = CustomUser.objects.nocache().get(pk=event.host_id)
        wanted[(host.pk, ContributionKind.EVENT_HOST.value)] = host
    helpers = event.helpers.nocache().all()
    if event.host_id is not None:
        helpers = helpers.exclude(pk=event.host_id)
    for helper in helpers:
        wanted[(helper.pk, ContributionKind.EVENT_HELPER.value)] = helper

    existing = ContributionEntry.objects.nocache().filter(
        organization=org, event=event, kind__in=EVENT_STAFF_KINDS
    )
    have: set[tuple[int, str]] = set()
    remove: list[int] = []
    refresh: list[int] = []
    for pk, user_id, kind, entry_at, entry_name in existing.values_list(
        "pk", "org_user__user_id", "kind", "occurred_at", "event_name"
    ):
        key = (user_id, kind)
        if key not in wanted or key in have:
            remove.append(pk)
            continue
        have.add(key)
        if entry_at != occurred_at or entry_name != event.name:
            refresh.append(pk)

    deleted = len(remove)
    if remove:
        ContributionEntry.objects.nocache().filter(pk__in=remove).delete()
    updated = 0
    if refresh:
        updated = (
            ContributionEntry.objects.nocache()
            .filter(pk__in=refresh)
            .update(
                occurred_at=occurred_at,
                event_name=event.name,
                updated_at=timezone.now(),
            )
        )
    created = 0
    for (_, kind), user in wanted.items():
        if (user.pk, kind) in have:
            continue
        award_entry(org=org, user=user, kind=kind, occurred_at=occurred_at, event=event)
        created += 1

    result = SyncResult(created=created, deleted=deleted, updated=updated)
    log.info(
        "event_staff_entries_synced",
        system="org",
        subsystem="contributions",
        org_id=org.pk,
        event_id=event.pk,
        created=created,
        deleted=deleted,
        updated=updated,
    )
    return result


@transaction.atomic
def create_manual_award(
    *,
    org: Organization,
    user: CustomUser,
    points: int,
    reason: str,
    on_date: date,
    actor: CustomUser | None,
    event: Event | None = None,
) -> ContributionEntry:
    points = _check_manual_points(points)
    cleaned = _check_reason(reason)
    _check_event(org, event)
    if not (
        OrgUser.objects.filter(user=user, organization=org).exists()
        or is_org_role_holder(user, org)
    ):
        raise ValueError("user is not a member of this organization")
    entry = award_entry(
        org=org,
        user=user,
        kind=ContributionKind.MANUAL,
        occurred_at=local_noon_utc(org, on_date),
        event=event,
        awarded_by=actor,
        reason=cleaned,
        points=points,
    )
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="award_points",
        target_user=user,
        details={"pk": entry.pk, "points": points, "reason": cleaned},
    )
    return entry


def _lock_entry(pk: int) -> ContributionEntry:
    """Raises ContributionEntry.DoesNotExist if a concurrent delete won."""
    return (
        ContributionEntry.objects.nocache()
        .select_for_update()
        .select_related("organization", "org_user__user")
        .get(pk=pk)
    )


@transaction.atomic
def update_manual_award(
    entry: ContributionEntry,
    *,
    actor: CustomUser | None,
    points: int | None = None,
    reason: str | None = None,
    on_date: date | None = None,
    event: Event | None | _Unset = UNSET,
) -> ContributionEntry:
    _require_manual(entry)
    org = entry.organization
    new_points = _check_manual_points(points) if points is not None else None
    new_reason = _check_reason(reason) if reason is not None else None
    new_occurred_at = local_noon_utc(org, on_date) if on_date is not None else None
    if event is not UNSET:
        _check_event(org, event)
    entry = _lock_entry(entry.pk)
    old = _manual_snapshot(entry)
    fields: list[str] = []
    if new_points is not None:
        entry.points = new_points
        fields.append("points")
    if new_reason is not None:
        entry.reason = new_reason
        fields.append("reason")
    if new_occurred_at is not None:
        entry.occurred_at = new_occurred_at
        fields.append("occurred_at")
    if event is not UNSET:
        entry.event = event
        entry.event_name = event.name if event is not None else ""
        fields += ["event", "event_name"]
    new = _manual_snapshot(entry)
    if new == old:
        return entry
    entry.save(update_fields=[*fields, "updated_at"])
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="edit_award",
        target_user=entry.org_user.user,
        details={"pk": entry.pk, "old": old, "new": new},
    )
    log.info(
        "manual_award_updated",
        system="org",
        subsystem="contributions",
        org_id=org.pk,
        entry_id=entry.pk,
        actor_id=actor.pk if actor is not None else None,
    )
    return entry


@transaction.atomic
def delete_manual_award(entry: ContributionEntry, *, actor: CustomUser | None) -> None:
    _require_manual(entry)
    entry = _lock_entry(entry.pk)
    pk = entry.pk
    org = entry.organization
    details = {"pk": pk, "points": entry.points, "reason": entry.reason}
    target = entry.org_user.user
    entry.delete()
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="delete_award",
        target_user=target,
        details=details,
    )
    log.info(
        "manual_award_deleted",
        system="org",
        subsystem="contributions",
        org_id=org.pk,
        entry_id=pk,
        actor_id=actor.pk if actor is not None else None,
    )


@transaction.atomic
def set_point_value(
    org: Organization,
    kind: str,
    points: int | None,
    *,
    actor: CustomUser | None,
    apply_to_past: bool = False,
    since: date | None = None,
) -> RescoreResult:
    if kind not in RATED_KINDS:
        raise ValueError(f"kind {str(kind)!r} has no point value")
    kind = ContributionKind(kind).value
    if points is not None and (
        not _is_int(points) or not 0 <= points <= POINT_VALUE_MAX
    ):
        raise ValueError(f"points must be an integer from 0 to {POINT_VALUE_MAX}")
    if since is not None and not apply_to_past:
        raise ValueError("since requires apply_to_past")

    old = points_for(org, kind)
    rows = ContributionPointValue.objects.nocache().filter(organization=org, kind=kind)
    if points is None:
        rows.delete()
        new = DEFAULT_POINTS[kind]
    else:
        ContributionPointValue.objects.update_or_create(
            organization=org,
            kind=kind,
            defaults={"points": points, "updated_by": actor},
        )
        new = points
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="set_point_value",
        details={"kind": kind, "old": old, "new": new},
    )

    changed = 0
    if apply_to_past:
        entries = ContributionEntry.objects.nocache().filter(
            organization=org, kind=kind
        )
        if since is not None:
            entries = entries.filter(occurred_at__gte=local_day_start_utc(org, since))
        changed = entries.update(points=new, updated_at=timezone.now())
        OrgLog.objects.create(
            organization=org,
            actor=actor,
            action="rescore",
            details={
                "kind": kind,
                "old": old,
                "new": new,
                "since": since.isoformat() if since is not None else None,
                "changed": changed,
            },
        )

    log.info(
        "point_value_set",
        system="org",
        subsystem="contributions",
        org_id=org.pk,
        kind=kind,
        old=old,
        new=new,
        apply_to_past=apply_to_past,
        since=since.isoformat() if since is not None else None,
        changed=changed,
        actor_id=actor.pk if actor is not None else None,
    )
    return RescoreResult(old=old, new=new, changed=changed)


@transaction.atomic
def delete_user_entries(user: CustomUser, *, actor: CustomUser | None) -> int:
    entries = ContributionEntry.objects.nocache().filter(org_user__user=user)
    per_org = {
        row["organization_id"]: row["count"]
        for row in entries.values("organization_id").annotate(count=Count("pk"))
    }
    if not per_org:
        return 0
    entries.delete()
    deleted = sum(per_org.values())
    for org_id, count in per_org.items():
        OrgLog.objects.create(
            organization_id=org_id,
            actor=actor,
            action="delete_user_contributions",
            target_user=user,
            details={"user_id": user.pk, "username": user.username, "count": count},
        )
    log.info(
        "contributions_deleted_for_user",
        system="org",
        subsystem="contributions",
        user_id=user.pk,
        actor_id=actor.pk if actor is not None else None,
        deleted=deleted,
        org_ids=sorted(per_org),
    )
    return deleted


@transaction.atomic
def reassign_member(drop: OrgUser, keep: OrgUser) -> int:
    if drop.organization_id != keep.organization_id:
        raise ValueError("cannot reassign contributions across organizations")
    if drop.pk == keep.pk:
        return 0
    entries = ContributionEntry.objects.nocache()
    kept_staff = set(
        entries.filter(
            org_user=keep, kind__in=EVENT_STAFF_KINDS, event__isnull=False
        ).values_list("event_id", "kind")
    )
    discard: list[int] = []
    move: list[int] = []
    for pk, event_id, kind in entries.filter(org_user=drop).values_list(
        "pk", "event_id", "kind"
    ):
        if event_id is not None and (event_id, kind) in kept_staff:
            discard.append(pk)
        else:
            move.append(pk)
    entries.filter(pk__in=discard).delete()
    moved = entries.filter(pk__in=move).update(org_user=keep, updated_at=timezone.now())

    hosted = entries.filter(
        org_user=keep, kind=ContributionKind.EVENT_HOST, event__isnull=False
    ).values("event_id")
    deduped, _ = entries.filter(
        org_user=keep, kind=ContributionKind.EVENT_HELPER, event_id__in=hosted
    ).delete()

    log.info(
        "contributions_member_reassigned",
        system="org",
        subsystem="contributions",
        org_id=keep.organization_id,
        drop_org_user_id=drop.pk,
        keep_org_user_id=keep.pk,
        moved=moved,
        discarded=len(discard),
        helper_deduped=deduped,
    )
    return moved


def repoint_user_attribution(drop: CustomUser, keep: CustomUser) -> int:
    return (
        ContributionEntry.objects.nocache()
        .filter(awarded_by=drop)
        .update(awarded_by=keep)
        + OrgFeature.objects.nocache().filter(enabled_by=drop).update(enabled_by=keep)
        + ContributionPointValue.objects.nocache()
        .filter(updated_by=drop)
        .update(updated_by=keep)
        + PromoTemplate.objects.filter(created_by=drop).update(created_by=keep)
    )


@transaction.atomic
def dedupe_event_staff(user: CustomUser) -> int:
    events = list(
        Event.objects.nocache()
        .select_for_update(of=("self",))
        .filter(
            pk__in=Event.objects.nocache().filter(host=user, helpers=user).values("pk")
        )
        .select_related("organization")
    )
    synced = 0
    for event in events:
        event.helpers.remove(user)
        if should_sync_staff(event):
            sync_event_staff_entries(event)
            synced += 1
    if not events:
        return 0
    invalidate_after_commit(*events)
    log.info(
        "event_staff_deduped",
        system="org",
        subsystem="contributions",
        user_id=user.pk,
        event_ids=[event.pk for event in events],
        synced=synced,
    )
    return len(events)
