from collections.abc import Iterable

from django.db.models import Q

from app.models import CustomUser, League
from org.models import OrgUser


def member_organization_ids(
    user: CustomUser,
    *,
    admin_org_ids: Iterable[int],
    staff_org_ids: Iterable[int],
) -> list[int]:
    member_ids = OrgUser.objects.filter(user=user).nocache().values_list(
        "organization_id", flat=True
    )
    league_org_ids = (
        League.objects.filter(Q(admins=user) | Q(staff=user), organization__isnull=False)
        .nocache()
        .values_list("organization_id", flat=True)
    )
    return sorted({*member_ids, *admin_org_ids, *staff_org_ids, *league_org_ids})
