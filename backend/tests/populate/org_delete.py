"""
Populate test data for the Organization Delete feature.

Creates ORG_DELETE_ORG (pk=10) with four distinct users:
- ORG_DELETE_OWNER  (pk=6000) — set as org.owner
- ORG_DELETE_ADMIN  (pk=6001) — added to org.admins
- ORG_DELETE_STAFF  (pk=6002) — added to org.staff
- ORG_DELETE_MEMBER (pk=6003) — plain OrgUser, no special role

PK note: Original target was pk=8 but `Auth Matrix Test Org` (from auth-matrix
branch) occupies that slot. Shifted to 10. If auth-matrix lands separately,
no remediation needed — PKs are independent.

Used by frontend/tests/playwright/e2e/17-org-delete/ to verify the
permission matrix on the Danger Zone UI.
"""

from django.utils import timezone

from app.cache_utils import invalidate_obj
from app.models import CustomUser, Organization, PositionsModel
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry
from org.models import ContributionEntry
from tests.data.models import TestUser
from tests.data.org_delete import (
    ORG_DELETE_ADMIN,
    ORG_DELETE_MEMBER,
    ORG_DELETE_ORG,
    ORG_DELETE_OWNER,
    ORG_DELETE_STAFF,
)
from tests.populate.utils import delete_ledger_for_users, ensure_org_user

# (user, points) manual awards, so deleting the org covers a ledger.
ORG_DELETE_LEDGER: list[tuple[TestUser, int]] = [
    (ORG_DELETE_ADMIN, 5),
    (ORG_DELETE_MEMBER, 2),
]


def _get_or_create_user(user_data: TestUser, force: bool) -> CustomUser:
    existing = CustomUser.objects.filter(pk=user_data.pk).first()
    if existing and not force:
        return existing
    if existing:
        delete_ledger_for_users([existing.pk])
        # Organization.owner is PROTECT; populate_org_delete sets it again.
        Organization.objects.filter(owner=existing).update(owner=None)
        existing.delete()
    positions = PositionsModel.objects.create()
    user = CustomUser(
        pk=user_data.pk,
        username=user_data.username,
        nickname=user_data.nickname,
        discordId=user_data.discord_id,
        steamid=user_data.get_steam_id_64(),
        positions=positions,
    )
    user.set_unusable_password()
    user.save()
    print(f"  Created user: {user_data.username} (pk={user_data.pk})")
    return user


def populate_org_delete(force: bool = False) -> None:
    print("Populating org delete test data...")

    org, created = Organization.objects.update_or_create(
        pk=ORG_DELETE_ORG.pk,
        defaults={
            "name": ORG_DELETE_ORG.name,
            "description": ORG_DELETE_ORG.description,
            "logo": "",
            "timezone": ORG_DELETE_ORG.timezone,
        },
    )
    print(
        f"  {'Created' if created else 'Updated'} organization: {ORG_DELETE_ORG.name} (pk={org.pk})"
    )

    owner = _get_or_create_user(ORG_DELETE_OWNER, force)
    admin = _get_or_create_user(ORG_DELETE_ADMIN, force)
    staff = _get_or_create_user(ORG_DELETE_STAFF, force)
    member = _get_or_create_user(ORG_DELETE_MEMBER, force)

    if org.owner_id != owner.pk:
        org.owner = owner
        org.save(update_fields=["owner"])
        print(f"  Set owner: {owner.username}")

    if owner not in org.admins.all():
        org.admins.add(owner)
    if admin not in org.admins.all():
        org.admins.add(admin)
        print(f"  Added admin: {admin.username}")

    if staff not in org.staff.all():
        org.staff.add(staff)
        print(f"  Added staff: {staff.username}")

    invalidate_obj(org)

    ensure_org_user(owner, org)
    ensure_org_user(admin, org)
    ensure_org_user(staff, org)
    ensure_org_user(member, org)

    ContributionEntry.objects.nocache().filter(organization=org).delete()
    users = {u.pk: u for u in (owner, admin, staff, member)}
    for data, points in ORG_DELETE_LEDGER:
        award_entry(
            org=org,
            user=users[data.pk],
            kind=ContributionKind.MANUAL,
            points=points,
            reason="Seeded award",
            occurred_at=timezone.now(),
            awarded_by=owner,
        )

    print(f"Org delete test data ready. Org pk={org.pk}")
