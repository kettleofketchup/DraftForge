"""Populate the MMR update request E2E data (tests.data.mmr_requests).

populate_mmr_requests_data creates org/league 60, members 8100-8102 at an
unverified 4200 org and league MMR, org staff 8103, league staff 8104 and
outsider 8105. reset_mmr_requests, behind POST /api/tests/mmr-requests/reset/,
deletes a member's requests (and their screenshots) and restores the baseline.
mmr_requests_test_data is the lookup the spec reads.
"""

from typing import Any

from django.db import transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, PositionsModel
from common.game import GameType
from league.models import League, LeagueUser
from org.mmr import LEAGUE_GAME
from org.models import MmrChangeRequest, Organization, OrgUser, OrgUserGameMmr
from tests.data.mmr_requests import (
    MMR_REQ_BASE_MMR,
    MMR_REQ_LEAGUE,
    MMR_REQ_LEAGUE_STAFF,
    MMR_REQ_MEMBER_APPROVE,
    MMR_REQ_MEMBER_REJECT,
    MMR_REQ_MEMBER_STAFFSET,
    MMR_REQ_MEMBERS,
    MMR_REQ_ORG,
    MMR_REQ_ORG_STAFF,
    MMR_REQ_OUTSIDER,
    MMR_REQ_USERS,
)
from tests.data.models import TestUser
from tests.populate.utils import ensure_league_user, ensure_org_user

MEMBER_PKS: frozenset[int] = frozenset(u.pk for u in MMR_REQ_MEMBERS if u.pk)


def _ensure_org_and_league() -> tuple[Organization, League]:
    org, _ = Organization.objects.update_or_create(
        pk=MMR_REQ_ORG.pk,
        defaults={
            "name": MMR_REQ_ORG.name,
            "description": MMR_REQ_ORG.description,
            "logo": "",
            "timezone": MMR_REQ_ORG.timezone,
            "members_private": False,
        },
    )
    league, _ = League.objects.update_or_create(
        pk=MMR_REQ_LEAGUE.pk,
        defaults={
            "steam_league_id": MMR_REQ_LEAGUE.steam_league_id,
            "name": MMR_REQ_LEAGUE.name,
            "organization": org,
            "timezone": MMR_REQ_LEAGUE.timezone,
        },
    )
    return org, league


def _ensure_user(data: TestUser) -> CustomUser:
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        user = CustomUser(pk=data.pk, positions=PositionsModel.objects.create())
        user.set_unusable_password()
    user.username = data.username
    user.nickname = data.nickname
    user.discordId = data.discord_id
    user.save()
    return user


def _restore_member(user: CustomUser, org: Organization, league: League) -> None:
    org_user = ensure_org_user(user, org, mmr=MMR_REQ_BASE_MMR)
    OrgUserGameMmr.objects.filter(org_user=org_user).exclude(
        game_type=GameType.DOTA2
    ).delete()
    OrgUserGameMmr.objects.filter(org_user=org_user).update(
        verified_at=None, verified_by=None
    )
    org_user.has_active_dota_mmr = False
    org_user.dota_mmr_last_verified = None
    org_user.save(update_fields=["has_active_dota_mmr", "dota_mmr_last_verified"])
    league_user = ensure_league_user(user, org_user, league)
    league_user.mmr = MMR_REQ_BASE_MMR
    league_user.mmr_verified_at = None
    league_user.mmr_verified_by = None
    league_user.save(update_fields=["mmr", "mmr_verified_at", "mmr_verified_by"])
    invalidate_after_commit(org_user, league_user, user)


@transaction.atomic
def populate_mmr_requests_data(force: bool = False) -> None:
    """Create the MMR request org, league, members and staff roles.

    Everything is updated in place; `force` also drops every request.
    """
    print("  Populating MMR update request E2E data...")
    org, league = _ensure_org_and_league()
    users = {data.pk: _ensure_user(data) for data in MMR_REQ_USERS}
    if force:
        MmrChangeRequest.objects.filter(organization=org).delete()
    for pk in MEMBER_PKS:
        _restore_member(users[pk], org, league)
    org.staff.add(users[MMR_REQ_ORG_STAFF.pk])
    league.staff.add(users[MMR_REQ_LEAGUE_STAFF.pk])
    invalidate_after_commit(org, league)
    print(f"    Created {MMR_REQ_ORG.name} with {len(MMR_REQ_USERS)} users")


def reset_mmr_requests(
    user_pk: int | None = None, members_private: bool = False
) -> None:
    """Delete a member's requests and files and restore 4200 unverified.

    With no `user_pk` every member is reset. The org's member list is set
    public, or private when `members_private`.
    """
    pks = MEMBER_PKS if user_pk is None else frozenset({user_pk})
    if not pks <= MEMBER_PKS:
        raise ValueError(f"Not an MMR request member: {user_pk}")
    with transaction.atomic():
        org, league = _ensure_org_and_league()
        if members_private:
            Organization.objects.filter(pk=org.pk).update(members_private=True)
        MmrChangeRequest.objects.filter(
            organization=org, subject_user_id__in=pks
        ).delete()
        for user in CustomUser.objects.filter(pk__in=pks):
            _restore_member(user, org, league)
        invalidate_after_commit(org, league)


def _user_payload(data: TestUser) -> dict[str, Any]:
    org_user = (
        OrgUser.objects.nocache()
        .filter(organization_id=MMR_REQ_ORG.pk, user_id=data.pk)
        .first()
    )
    league_user = (
        LeagueUser.objects.nocache()
        .filter(league_id=MMR_REQ_LEAGUE.pk, user_id=data.pk)
        .first()
    )
    return {
        "pk": data.pk,
        "username": data.username,
        "nickname": data.nickname,
        "org_user_pk": org_user.pk if org_user else None,
        "league_user_pk": league_user.pk if league_user else None,
    }


def mmr_requests_test_data() -> dict[str, Any]:
    """PKs and names the spec looks up (never hardcoded there)."""
    return {
        "org": {"pk": MMR_REQ_ORG.pk, "name": MMR_REQ_ORG.name},
        "league": {"pk": MMR_REQ_LEAGUE.pk, "name": MMR_REQ_LEAGUE.name},
        "base_mmr": MMR_REQ_BASE_MMR,
        "game_types": {
            "dota2": int(GameType.DOTA2),
            "deadlock": int(GameType.DEADLOCK),
            "league": int(LEAGUE_GAME),
        },
        "users": {
            "member_approve": _user_payload(MMR_REQ_MEMBER_APPROVE),
            "member_reject": _user_payload(MMR_REQ_MEMBER_REJECT),
            "member_staffset": _user_payload(MMR_REQ_MEMBER_STAFFSET),
            "org_staff": _user_payload(MMR_REQ_ORG_STAFF),
            "league_staff": _user_payload(MMR_REQ_LEAGUE_STAFF),
            "outsider": _user_payload(MMR_REQ_OUTSIDER),
        },
    }
