from collections.abc import Sequence

from org.models import Organization, OrgSettings
from org.settings_service import get_org_settings


def set_org_override_policy(
    org: Organization, policy: str, codes: Sequence[str] = ("over_capacity",)
) -> None:
    row = get_org_settings(org)
    OrgSettings.objects.filter(pk=row.pk).update(
        staff_override_policy=policy, staff_override_warning_codes=list(codes)
    )
