"""Populate and reset the MMR sync API E2E data (tests.data.mmr_sync).

reset_mmr_sync_data, behind POST /api/tests/mmr-sync/reset/, creates or
updates the orgs and users, deletes every token, usage row and limits
override of the two orgs, puts the switches and roles back and resets the
sync target's org MMR. populate_mmr_sync_data runs the same reset.
"""

from typing import Any

from django.db import transaction

from app.cache_utils import invalidate_model, invalidate_obj
from app.models import CustomUser, PositionsModel
from common.game import GameType
from org.features import FeatureKey, set_org_feature
from org.mmr import set_org_mmr
from org.models import (
    Organization,
    OrgApiLimits,
    OrgApiToken,
    OrgApiTokenUsage,
    OrgUser,
)
from tests.data.mmr_sync import (
    MMR_SYNC_LOCKED_ORG,
    MMR_SYNC_ORG,
    MMR_SYNC_ORGS,
    MMR_SYNC_ROLE_USERS,
    MMR_SYNC_ROLES,
    MMR_SYNC_UNLOCKED_PKS,
    MS_PLAYER,
    MS_PLAYER_SEED_MMR,
)
from tests.data.models import TestOrganization, TestUser
from tests.populate.utils import ensure_org_user


def _ensure_org(data: TestOrganization) -> Organization:
    org, _ = Organization.objects.update_or_create(
        pk=data.pk,
        defaults={
            "name": data.name,
            "description": data.description,
            "logo": "",
            "timezone": data.timezone,
        },
    )
    return org


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.steam_account_id = data.get_steam_account_id()
    user.steamid = None
    user.save()
    return user


def reset_mmr_sync_data() -> dict[str, Any]:
    """Put the MMR sync orgs, users, switches and roles back to the seed."""
    with transaction.atomic():
        orgs = {o.pk: _ensure_org(o) for o in MMR_SYNC_ORGS}
        users = {u.pk: _ensure_user(u) for u in MMR_SYNC_ROLE_USERS.values()}
        org_pks = list(orgs)
        OrgApiTokenUsage.objects.filter(organization_id__in=org_pks).delete()
        OrgApiToken.objects.filter(organization_id__in=org_pks).delete()
        OrgApiLimits.objects.filter(organization_id__in=org_pks).delete()
        for org_data, owner, admins, staff, members in MMR_SYNC_ROLES:
            org = orgs[org_data.pk]
            org.owner = users[owner.pk]
            org.save(update_fields=["owner"])
            org.admins.set([users[u.pk] for u in admins])
            org.staff.set([users[u.pk] for u in staff])
            org.promoters.clear()
            member_pks = [m.pk for m in members]
            OrgUser.objects.nocache().filter(organization=org).exclude(
                user_id__in=member_pks
            ).delete()
            for pk in member_pks:
                ensure_org_user(users[pk], org)
            for key in FeatureKey:
                set_org_feature(
                    org,
                    key,
                    enabled=key == FeatureKey.MMR_SYNC
                    and org.pk in MMR_SYNC_UNLOCKED_PKS,
                    actor=None,
                )
        player = OrgUser.objects.nocache().get(
            organization=orgs[MMR_SYNC_ORG.pk], user_id=MS_PLAYER.pk
        )
        set_org_mmr(player, GameType.DOTA2, MS_PLAYER_SEED_MMR, mark_verified=False)
    invalidate_model(OrgUser)
    invalidate_obj(player)
    for org in orgs.values():
        invalidate_obj(org)
    for user in users.values():
        invalidate_obj(user)
    return mmr_sync_test_data()


def populate_mmr_sync_data(force: bool = False) -> None:
    """Create the MMR sync orgs and users; `force` changes nothing."""
    print("  Populating MMR sync API E2E data...")
    reset_mmr_sync_data()
    print(f"    Created {', '.join(o.name for o in MMR_SYNC_ORGS)}")


def mmr_sync_test_data() -> dict[str, Any]:
    """PKs and names the specs look up (never hardcoded there)."""
    return {
        "orgs": {
            "unlocked": {"pk": MMR_SYNC_ORG.pk, "name": MMR_SYNC_ORG.name},
            "locked": {
                "pk": MMR_SYNC_LOCKED_ORG.pk,
                "name": MMR_SYNC_LOCKED_ORG.name,
            },
        },
        "users": {
            role: {"pk": u.pk, "username": u.username}
            for role, u in MMR_SYNC_ROLE_USERS.items()
        },
        "player": {
            "pk": MS_PLAYER.pk,
            "steam_id": MS_PLAYER.get_steam_account_id(),
            "mmr": MS_PLAYER_SEED_MMR,
        },
    }
