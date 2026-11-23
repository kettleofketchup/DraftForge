import copy
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from org.leadership.constants import (
    BOOL_SETTINGS,
    EDITABLE_SETTINGS_FIELDS,
    NULLABLE_SETTINGS,
    SETTINGS_RANGES,
)
from org.leadership.errors import ReviewRefused
from org.leadership.kinds import DEFAULT_POINTS, RATED_KINDS
from org.leadership.release import release_floor, released_snapshots
from org.models import ContributionPointValue, Organization, OrgLog
from org.models_leadership import EventCaptain, OrgLeadershipSettings
from org.standing import ledger
from telemetry.logging import get_logger

log = get_logger(__name__)

RATED_KIND_VALUES: frozenset[str] = frozenset(k.value for k in RATED_KINDS)
POINT_VALUE_MAX: int = 1000
GATE_FIELDS: frozenset[str] = frozenset(
    {"require_staff_release", "auto_release_after_hours", "rating_min_reviewers"}
)


def _org_id(org: Organization | int) -> int:
    return org if isinstance(org, int) else org.pk


def get_leadership_settings(
    org: Organization | int, *, create: bool = False
) -> OrgLeadershipSettings:
    org_id = _org_id(org)
    row = OrgLeadershipSettings.objects.filter(organization_id=org_id).first()
    if row is not None:
        return row
    if create:
        row, _ = OrgLeadershipSettings.objects.nocache().get_or_create(
            organization_id=org_id
        )
        return row
    return OrgLeadershipSettings(organization_id=org_id)


def moderator_count(org: Organization) -> int:
    return (
        CustomUser.objects.filter(
            Q(pk=org.owner_id) | Q(admin_organizations=org) | Q(staff_organizations=org)
        )
        .distinct()
        .count()
    )


def leadership_points(org: Organization) -> dict[str, int]:
    return ledger.points_table(org, [k.value for k in RATED_KINDS])


def kind_points(org: Organization) -> list[dict[str, Any]]:
    overrides = dict(
        ContributionPointValue.objects.nocache()
        .filter(organization=org, kind__in=RATED_KIND_VALUES)
        .values_list("kind", "points")
    )
    return [
        {
            "kind": kind.value,
            "label": kind.label,
            "default": DEFAULT_POINTS[kind.value],
            "points": overrides.get(kind.value, DEFAULT_POINTS[kind.value]),
            "overridden": kind.value in overrides,
        }
        for kind in RATED_KINDS
    ]


def _validate_changes(changes: Mapping[str, object]) -> None:
    unknown = set(changes) - set(EDITABLE_SETTINGS_FIELDS)
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    for field, value in changes.items():
        if value is None:
            if field in NULLABLE_SETTINGS:
                continue
            raise ValueError(f"{field} cannot be null.")
        if field in BOOL_SETTINGS:
            if not isinstance(value, bool):
                raise ValueError(f"{field} must be true or false.")
            continue
        bounds = SETTINGS_RANGES.get(field)
        if bounds is None:
            continue
        low, high = bounds
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{field} must be a number.")
        if not low <= value <= high:
            raise ValueError(f"{field} must be between {low} and {high}.")


def _validate_points(points: Mapping[str, int | None]) -> None:
    for kind, value in points.items():
        if kind not in RATED_KIND_VALUES:
            raise ValueError(f"kind {kind!r} has no point value")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Points for {kind!r} must be an integer.")
        if not 0 <= value <= POINT_VALUE_MAX:
            raise ValueError(f"Points for {kind!r} must be 0..{POINT_VALUE_MAX}.")


def _apply_points(
    org: Organization, actor: CustomUser, points: Mapping[str, int | None]
) -> dict[str, dict[str, int | None]]:
    current = dict(
        ContributionPointValue.objects.nocache()
        .select_for_update()
        .filter(organization=org, kind__in=list(points))
        .values_list("kind", "points")
    )
    changed: dict[str, dict[str, int | None]] = {}
    for kind, new in points.items():
        old = current.get(kind)
        if old == new:
            continue
        if new is None:
            ContributionPointValue.objects.filter(organization=org, kind=kind).delete()
        else:
            ContributionPointValue.objects.update_or_create(
                organization=org,
                kind=kind,
                defaults={"points": new, "updated_by": actor},
            )
        changed[kind] = {"old": old, "new": new}
    return changed


def _released_ids(
    org: Organization, settings: OrgLeadershipSettings, now: datetime
) -> set[int]:
    return set(
        released_snapshots(org.pk, now=now, settings=settings).values_list(
            "pk", flat=True
        )
    )


def _loosens_gate(old: OrgLeadershipSettings, new: OrgLeadershipSettings) -> bool:
    if not new.require_staff_release:
        return True
    old_hours = old.auto_release_after_hours
    new_hours = new.auto_release_after_hours
    if new_hours is not None and (old_hours is None or new_hours < old_hours):
        return True
    return release_floor(new.rating_min_reviewers) < release_floor(
        old.rating_min_reviewers
    )


def _refuses_self_release(
    org: Organization,
    *,
    actor: CustomUser,
    old: OrgLeadershipSettings,
    new: OrgLeadershipSettings,
    before: set[int],
    unlocked: set[int],
) -> bool:
    if not old.require_staff_release:
        return False
    own = EventCaptain.objects.nocache().filter(
        organization_id=org.pk, captain__user_id=actor.pk
    )
    if own.filter(pk__in=unlocked).exists():
        return True
    return (
        _loosens_gate(old, new)
        and own.filter(voided_at__isnull=True, released_at__isnull=True)
        .exclude(pk__in=before)
        .exists()
    )


def _apply_gate_change(
    org: Organization,
    *,
    actor: CustomUser,
    old: OrgLeadershipSettings,
    new: OrgLeadershipSettings,
    now: datetime,
) -> tuple[list[EventCaptain], int]:
    before = _released_ids(org, old, now)
    after = _released_ids(org, new, now)
    unlocked = after - before
    if _refuses_self_release(
        org, actor=actor, old=old, new=new, before=before, unlocked=unlocked
    ):
        raise ReviewRefused(
            "would_release_own_results",
            409,
            "This change would release your own results. "
            "Ask another moderator to release them first.",
        )
    stamped: list[EventCaptain] = []
    if new.require_staff_release:
        stamped = list(
            EventCaptain.objects.nocache().filter(
                pk__in=before, released_at__isnull=True
            )
        )
        if stamped:
            EventCaptain.objects.filter(pk__in=[s.pk for s in stamped]).update(
                released_at=now, released_by=None
            )
    return stamped, len(unlocked)


def update_leadership_settings(
    org: Organization,
    *,
    actor: CustomUser,
    changes: Mapping[str, object],
    points: Mapping[str, int | None] | None = None,
) -> OrgLeadershipSettings:
    _validate_changes(changes)
    _validate_points(points or {})
    with transaction.atomic():
        existing = get_leadership_settings(org, create=True)
        row = (
            OrgLeadershipSettings.objects.nocache()
            .select_for_update()
            .get(pk=existing.pk)
        )
        changed_fields = [
            f
            for f in EDITABLE_SETTINGS_FIELDS
            if f in changes and getattr(row, f) != changes[f]
        ]
        old = copy.copy(row)
        for field in changed_fields:
            setattr(row, field, changes[field])
        if row.max_age_days < row.half_life_days:
            raise ValueError("Max age must be at least the half-life.")
        gate_changed = bool(GATE_FIELDS.intersection(changed_fields))
        stamped: list[EventCaptain] = []
        unlocked = 0
        if gate_changed:
            stamped, unlocked = _apply_gate_change(
                org, actor=actor, old=old, new=row, now=timezone.now()
            )
        changed_points = _apply_points(org, actor, points or {})
        if not changed_fields and not changed_points:
            return row
        if changed_fields:
            row.updated_by = actor
            row.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
            invalidate_after_commit(*stamped, row)
        details: dict[str, Any] = {
            "changed_fields": changed_fields,
            "points": changed_points,
        }
        release_fields: dict[str, int] = {}
        if gate_changed:
            release_fields = {
                "release_stamped": len(stamped),
                "release_unlocked": unlocked,
            }
            details.update(release_fields)
        OrgLog.objects.create(
            organization=org,
            actor=actor,
            action="update_leadership_settings",
            details=details,
        )
        org_id = org.pk
        actor_id = actor.pk
        changed_kinds = sorted(changed_points)
        transaction.on_commit(
            lambda: log.info(
                "leadership_settings_updated",
                system="org",
                subsystem="leadership",
                org_id=org_id,
                actor_id=actor_id,
                changed_fields=changed_fields,
                changed_kinds=changed_kinds,
                **release_fields,
            )
        )
    return row
