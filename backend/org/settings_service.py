from collections.abc import Mapping

from django.db import transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Organization, OrgLog
from org import settings_constants
from org.models import OrgSettings
from org.settings_constants import StaffOverridePolicy
from telemetry.logging import get_logger

__all__ = [
    "EDITABLE_FIELDS",
    "get_org_settings",
    "normalize_warning_codes",
    "update_org_settings",
    "validate_policy",
]

log = get_logger(__name__)

EDITABLE_FIELDS: tuple[str, ...] = (
    "staff_override_policy",
    "staff_override_warning_codes",
)


def _org_id(org: Organization | int) -> int:
    return org if isinstance(org, int) else org.pk


def normalize_warning_codes(codes: object) -> list[str]:
    if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
        raise ValueError("Warning codes must be a list of strings")
    all_codes = settings_constants.ALL_CODES
    unknown = [c for c in dict.fromkeys(codes) if c not in all_codes]
    if unknown:
        raise ValueError(f"Unknown warning code(s): {', '.join(unknown)}")
    wanted = set(codes)
    return [c for c in all_codes if c in wanted]


def validate_policy(policy: object) -> str:
    if not isinstance(policy, str) or policy not in StaffOverridePolicy.values:
        raise ValueError(f"Unknown staff override policy: {policy!r}")
    return policy


def _cached_row(org_id: int) -> OrgSettings | None:
    return OrgSettings.objects.filter(organization_id=org_id).first()


def get_org_settings(org: Organization | int) -> OrgSettings:
    """Return the org's settings row, creating it with defaults on first read.

    Always use this, never ``org.settings``. An int must be an existing
    organization id.
    """
    org_id = _org_id(org)
    row = _cached_row(org_id)
    if row is not None:
        return row
    row, created = OrgSettings.objects.nocache().get_or_create(organization_id=org_id)
    if created:
        transaction.on_commit(
            lambda: log.info(
                "org_settings_created",
                system="org",
                subsystem="settings",
                org_id=org_id,
            )
        )
    return row


def update_org_settings(
    org: Organization,
    *,
    actor: CustomUser | None,
    changes: Mapping[str, object],
) -> OrgSettings:
    with transaction.atomic():
        existing = get_org_settings(org)
        row = OrgSettings.objects.nocache().select_for_update().get(pk=existing.pk)

        updates: dict[str, object] = {}
        for field in EDITABLE_FIELDS:
            if field not in changes:
                continue
            value = changes[field]
            if field == "staff_override_policy":
                value = validate_policy(value)
            elif field == "staff_override_warning_codes":
                value = normalize_warning_codes(value)
            updates[field] = value

        changed_fields = [
            field for field, value in updates.items() if getattr(row, field) != value
        ]
        if not changed_fields:
            return row

        for field in changed_fields:
            setattr(row, field, updates[field])
        row.save(update_fields=[*changed_fields, "updated_at"])
        invalidate_after_commit(row)
        OrgLog.objects.create(
            organization=org,
            actor=actor,
            action="update",
            details={"area": "settings", "changed_fields": changed_fields},
        )

        org_id = org.pk
        actor_id = actor.pk if actor else None
        policy = row.staff_override_policy
        code_count = len(row.staff_override_warning_codes)
        transaction.on_commit(
            lambda: log.info(
                "org_settings_updated",
                system="org",
                subsystem="settings",
                org_id=org_id,
                actor_id=actor_id,
                changed_fields=changed_fields,
                staff_override_policy=policy,
                warning_code_count=code_count,
            )
        )

    return row
