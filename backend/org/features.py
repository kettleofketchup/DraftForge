from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Organization, OrgLog
from org.feature_keys import FeatureKey
from org.models import OrgFeature
from org.promotion import starter
from telemetry.logging import get_logger

__all__ = [
    "FeatureKey",
    "active_features",
    "org_has_feature",
    "set_org_feature",
]

log = get_logger(__name__)


def _org_id(org: Organization | int) -> int:
    return org if isinstance(org, int) else org.pk


def org_has_feature(org: Organization | int, feature: FeatureKey | str) -> bool:
    return (
        OrgFeature.objects.nocache()
        .filter(organization_id=_org_id(org), feature=str(feature), enabled=True)
        .exists()
    )


def active_features(org: Organization | int) -> list[str]:
    return list(
        OrgFeature.objects.nocache()
        .filter(organization_id=_org_id(org), enabled=True)
        .order_by("feature")
        .values_list("feature", flat=True)
    )


def set_org_feature(
    org: Organization,
    feature: FeatureKey,
    *,
    enabled: bool,
    actor: CustomUser | None,
    notes: str | None = None,
) -> OrgFeature:
    key = FeatureKey(feature)
    with transaction.atomic():
        row, created = (
            OrgFeature.objects.nocache()
            .select_for_update()
            .get_or_create(organization=org, feature=key.value)
        )
        enabled_changed = row.enabled != enabled
        notes_changed = notes is not None and notes != row.notes

        if not created and not enabled_changed and not notes_changed:
            return row

        if enabled_changed or notes_changed:
            row.enabled = enabled
            if enabled_changed and enabled:
                row.enabled_by = actor
                row.enabled_at = timezone.now()
            if notes_changed:
                row.notes = notes
            row.save()
            if enabled_changed and enabled and key == FeatureKey.PROMOTION:
                starter.seed_starter_template(org, actor)

        if row.enabled or not created:
            OrgLog.objects.create(
                organization=org,
                actor=actor,
                action="enable_feature" if enabled else "disable_feature",
                details={"feature": key.value, "notes": row.notes},
            )
            invalidate_after_commit(org)
        transaction.on_commit(
            lambda: log.info(
                "org_feature_set",
                system="org",
                subsystem="features",
                org_id=org.pk,
                feature=key.value,
                enabled=enabled,
                enabled_changed=enabled_changed,
                notes_changed=notes_changed,
                created=created,
                actor_id=actor.pk if actor else None,
            )
        )

    return row
