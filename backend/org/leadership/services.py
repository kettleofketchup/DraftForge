from collections.abc import Mapping, Sequence
from typing import Any

from django.db import transaction
from django.db.models import ProtectedError, RestrictedError

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from org.leadership.constants import EDITABLE_SETTINGS_FIELDS, MAX_ACTIVE_TRAITS
from org.leadership.kinds import DEFAULT_POINTS, RATED_KINDS
from org.leadership.store import ensure_traits, get_leadership_settings
from org.models import ContributionPointValue, Organization, OrgLog
from org.models_leadership import CaptainTrait, OrgLeadershipSettings
from telemetry.logging import get_logger

log = get_logger(__name__)

RATED_KIND_VALUES: frozenset[str] = frozenset(k.value for k in RATED_KINDS)


class TraitInUse(Exception):
    pass


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


def _set_kind_points(
    org: Organization, actor: CustomUser, changes: Mapping[str, int | None]
) -> list[str]:
    changed: list[str] = []
    for kind, points in changes.items():
        if kind not in RATED_KIND_VALUES:
            raise ValueError(f"kind {kind!r} has no point value")
        rows = ContributionPointValue.objects.nocache().filter(
            organization=org, kind=kind
        )
        if points is None:
            if rows.delete()[0]:
                changed.append(kind)
            continue
        _, created = ContributionPointValue.objects.update_or_create(
            organization=org,
            kind=kind,
            defaults={"points": points, "updated_by": actor},
        )
        changed.append(kind)
    return changed


def update_settings(
    org: Organization,
    *,
    actor: CustomUser,
    changes: Mapping[str, object],
    points: Mapping[str, int | None] | None = None,
) -> OrgLeadershipSettings:
    unknown = set(changes) - set(EDITABLE_SETTINGS_FIELDS)
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
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
        changed_kinds = _set_kind_points(org, actor, points or {})
        if not changed_fields and not changed_kinds:
            return row
        if changed_fields:
            row.updated_by = actor
            row.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
            invalidate_after_commit(row)
        OrgLog.objects.create(
            organization=org,
            actor=actor,
            action="update_leadership_settings",
            details={"changed_fields": changed_fields, "changed_kinds": changed_kinds},
        )
        log.info(
            "leadership_settings_updated",
            system="org",
            subsystem="leadership",
            org_id=org.pk,
            actor_id=actor.pk,
            changed_fields=changed_fields,
            changed_kinds=changed_kinds,
        )
    return row


@transaction.atomic
def upsert_traits(
    org: Organization, *, actor: CustomUser, items: Sequence[Mapping[str, Any]]
) -> list[CaptainTrait]:
    existing = {t.key: t for t in ensure_traits(org)}
    for item in items:
        trait = existing.get(item["key"])
        if trait is None:
            trait = CaptainTrait(organization=org, key=item["key"])
            existing[trait.key] = trait
        trait.label = item.get("label", trait.label)
        trait.order = item.get("order", trait.order)
        trait.active = item.get("active", trait.active)
        if not trait.label:
            raise ValueError(f"Trait {trait.key!r} needs a label.")
    if sum(1 for t in existing.values() if t.active) > MAX_ACTIVE_TRAITS:
        raise ValueError(f"At most {MAX_ACTIVE_TRAITS} traits can be active.")
    if not any(t.active for t in existing.values()):
        raise ValueError("Keep at least one trait active.")
    for trait in existing.values():
        trait.save()
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="update_captain_traits",
        details={"keys": sorted(i["key"] for i in items)},
    )
    return list(CaptainTrait.objects.nocache().filter(organization=org))


@transaction.atomic
def delete_trait(org: Organization, *, actor: CustomUser, key: str) -> None:
    traits = {t.key: t for t in ensure_traits(org)}
    trait = traits.get(key)
    if trait is None:
        raise CaptainTrait.DoesNotExist(key)
    if trait.scores.exists():
        raise TraitInUse(key)
    if trait.active and sum(1 for t in traits.values() if t.active) <= 1:
        raise ValueError("Keep at least one trait active.")
    try:
        trait.delete()
    except (ProtectedError, RestrictedError) as exc:
        raise TraitInUse(key) from exc
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="update_captain_traits",
        details={"deleted": key},
    )
