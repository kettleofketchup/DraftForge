from collections.abc import Iterable

from django.db.models import Q
from django.contrib.auth.models import AnonymousUser

from app.models import CustomUser, League, Organization
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


def viewer_member_organization_ids(user: CustomUser | AnonymousUser) -> list[int]:
    """member_organization_ids for a request user, resolving admin and staff orgs itself."""
    if not user.is_authenticated:
        return []
    admin_ids = (
        Organization.objects.filter(Q(owner=user) | Q(admins=user))
        .nocache()
        .values_list("pk", flat=True)
    )
    staff_ids = (
        Organization.objects.filter(staff=user).nocache().values_list("pk", flat=True)
    )
    return member_organization_ids(
        user, admin_org_ids=admin_ids, staff_org_ids=staff_ids
    )
