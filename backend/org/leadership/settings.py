from collections.abc import Mapping
from typing import Any

from django.db import transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from org.leadership.constants import EDITABLE_SETTINGS_FIELDS, SETTINGS_RANGES
from org.leadership.kinds import DEFAULT_POINTS, RATED_KINDS
from org.models import ContributionPointValue, Organization, OrgLog
from org.models_leadership import OrgLeadershipSettings
from org.standing import ledger
from telemetry.logging import get_logger

log = get_logger(__name__)

RATED_KIND_VALUES: frozenset[str] = frozenset(k.value for k in RATED_KINDS)
POINT_VALUE_MAX: int = 1000


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
        for field in changed_fields:
            setattr(row, field, changes[field])
        if row.max_age_days < row.half_life_days:
            raise ValueError("Max age must be at least the half-life.")
        changed_points = _apply_points(org, actor, points or {})
        if not changed_fields and not changed_points:
            return row
        if changed_fields:
            row.updated_by = actor
            row.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
            invalidate_after_commit(row)
        OrgLog.objects.create(
            organization=org,
            actor=actor,
            action="update_leadership_settings",
            details={"changed_fields": changed_fields, "points": changed_points},
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
            )
        )
    return row
