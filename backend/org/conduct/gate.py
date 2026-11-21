from dataclasses import dataclass

from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.models import Organization
from org.models_conduct import OrgConductSettings


def _org_id(org: Organization | int) -> int:
    return org if isinstance(org, int) else org.pk


def get_conduct_settings(
    org: Organization | int, *, create: bool = False
) -> OrgConductSettings:
    org_id = _org_id(org)
    settings = OrgConductSettings.objects.filter(organization_id=org_id).first()
    if settings is not None:
        return settings
    if create:
        settings, _ = OrgConductSettings.objects.nocache().get_or_create(
            organization_id=org_id
        )
        return settings
    return OrgConductSettings(organization_id=org_id)


@dataclass(frozen=True)
class ConductGate:
    org_id: int | None
    feature_on: bool
    settings: OrgConductSettings | None
    enforcement_active: bool

    @property
    def back_of_line(self) -> bool:
        return (
            self.enforcement_active
            and self.settings is not None
            and self.settings.back_of_line_enabled
        )


GATE_OFF = ConductGate(
    org_id=None, feature_on=False, settings=None, enforcement_active=False
)


def conduct_gate(org: Organization | int | None) -> ConductGate:
    if org is None:
        return GATE_OFF
    org_id = _org_id(org)
    if not org_has_feature(org_id, FeatureKey.CONDUCT):
        return ConductGate(
            org_id=org_id, feature_on=False, settings=None, enforcement_active=False
        )
    settings = get_conduct_settings(org_id)
    enforcement_active = (
        settings.back_of_line_enabled
        or settings.require_approval_enabled
        or settings.block_enabled
    )
    return ConductGate(
        org_id=org_id,
        feature_on=True,
        settings=settings,
        enforcement_active=enforcement_active,
    )
