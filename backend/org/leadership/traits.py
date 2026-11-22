from collections.abc import Sequence
from typing import NotRequired, TypedDict

from django.core.exceptions import ValidationError
from django.core.validators import validate_slug
from django.db import transaction

from app.models import CustomUser
from org.leadership.constants import DEFAULT_TRAITS, MAX_ACTIVE_TRAITS
from org.models import Organization, OrgLog
from org.models_leadership import CaptainTrait, CaptainTraitScore
from telemetry.logging import get_logger

log = get_logger(__name__)

TRAIT_FIELDS: tuple[str, ...] = ("label", "order", "active")
TRAIT_KEY_MAX_LENGTH: int = 32


class TraitInUse(Exception):
    pass


class TraitItem(TypedDict):
    key: str
    label: NotRequired[str]
    order: NotRequired[int]
    active: NotRequired[bool]


def _org_id(org: Organization | int) -> int:
    return org if isinstance(org, int) else org.pk


def default_traits(org_id: int) -> list[CaptainTrait]:
    return [
        CaptainTrait(organization_id=org_id, key=key, label=label, order=i)
        for i, (key, label) in enumerate(DEFAULT_TRAITS)
    ]


def effective_traits(
    org_id: Organization | int, *, active_only: bool = False
) -> list[CaptainTrait]:
    pk = _org_id(org_id)
    traits = list(CaptainTrait.objects.nocache().filter(organization_id=pk))
    traits = traits or default_traits(pk)
    return [t for t in traits if t.active] if active_only else traits


def materialize_traits(org_id: Organization | int) -> list[CaptainTrait]:
    pk = _org_id(org_id)
    rows = CaptainTrait.objects.nocache().filter(organization_id=pk)
    if not rows.exists():
        CaptainTrait.objects.bulk_create(default_traits(pk), ignore_conflicts=True)
    return list(rows.all())


def _log_on_commit(event: str, org_id: int, actor_id: int, **fields: object) -> None:
    transaction.on_commit(
        lambda: log.info(
            event,
            system="org",
            subsystem="leadership",
            org_id=org_id,
            actor_id=actor_id,
            **fields,
        )
    )


@transaction.atomic
def upsert_traits(
    org: Organization, *, actor: CustomUser, items: Sequence[TraitItem]
) -> list[CaptainTrait]:
    existing = {t.key: t for t in materialize_traits(org.pk)}
    created: list[str] = []
    updated: list[str] = []
    dirty: dict[str, CaptainTrait] = {}
    for item in items:
        key = item["key"]
        try:
            validate_slug(key)
            if len(key) > TRAIT_KEY_MAX_LENGTH:
                raise ValidationError("too long")
        except ValidationError as exc:
            raise ValueError(f"Trait key {key!r} must be a slug.") from exc
        trait = existing.get(key)
        if trait is None:
            trait = CaptainTrait(organization=org, key=key, order=len(existing))
            existing[key] = trait
            created.append(key)
        changed = False
        for field in TRAIT_FIELDS:
            if field in item and getattr(trait, field) != item[field]:
                setattr(trait, field, item[field])
                changed = True
        if not trait.label:
            raise ValueError(f"Trait {key!r} needs a label.")
        if trait.pk is None or changed:
            dirty[key] = trait
            if trait.pk is not None and key not in updated:
                updated.append(key)
    active = sum(1 for t in existing.values() if t.active)
    if active > MAX_ACTIVE_TRAITS:
        raise ValueError(f"At most {MAX_ACTIVE_TRAITS} traits can be active.")
    if active == 0:
        raise ValueError("Keep at least one trait active.")
    for trait in dirty.values():
        trait.save()
    if dirty:
        OrgLog.objects.create(
            organization=org,
            actor=actor,
            action="update_captain_traits",
            details={"created": created, "updated": updated},
        )
        _log_on_commit(
            "leadership_traits_updated",
            org.pk,
            actor.pk,
            created=created,
            updated=updated,
        )
    return list(CaptainTrait.objects.nocache().filter(organization=org))


@transaction.atomic
def delete_trait(org: Organization, *, key: str, actor: CustomUser) -> None:
    traits = {t.key: t for t in materialize_traits(org.pk)}
    trait = traits.get(key)
    if trait is None:
        raise CaptainTrait.DoesNotExist(key)
    if CaptainTraitScore.objects.nocache().filter(trait=trait).exists():
        raise TraitInUse(key)
    if trait.active and sum(1 for t in traits.values() if t.active) <= 1:
        raise ValueError("Keep at least one trait active.")
    trait.delete()
    OrgLog.objects.create(
        organization=org,
        actor=actor,
        action="update_captain_traits",
        details={"deleted": [key]},
    )
    _log_on_commit("leadership_trait_deleted", org.pk, actor.pk, key=key)
