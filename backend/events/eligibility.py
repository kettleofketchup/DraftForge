"""Which signup requirements a user does not meet for an event.

Generic requirements apply to every game; game-specific ones come from
``REQUIREMENT_CHECKS`` keyed by ``event.game_type``. Add a game by
registering a ``GameRequirements`` implementation there.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from app.models import CustomUser, GameType
from events.models import Event
from events.schemas import DotaModalConfig, dota_require_screenshot
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile

# Range of the CustomUser.steam_account_id IntegerField.
STEAM_ACCOUNT_ID_MAX = 2**31 - 1


class Unmet(StrEnum):
    STEAM_ID_MISSING = "steam_id_missing"
    MMR_UNVERIFIED = "mmr_unverified"
    PROFILE_INCOMPLETE = "profile_incomplete"
    DOTA_RANK_UNDECLARED = "dota_rank_undeclared"
    RANK_TYPE_DISALLOWED = "rank_type_disallowed"
    RANK_SCREENSHOT_MISSING = "rank_screenshot_missing"
    BATTLECUP_SCREENSHOT_MISSING = "battlecup_screenshot_missing"
    BELOW_MIN_MMR = "below_min_mmr"


UNMET_LABELS: dict[Unmet, str] = {
    Unmet.STEAM_ID_MISSING: "Steam friend ID missing",
    Unmet.MMR_UNVERIFIED: "MMR not verified",
    Unmet.PROFILE_INCOMPLETE: "Profile incomplete",
    Unmet.DOTA_RANK_UNDECLARED: "Rank not declared",
    Unmet.RANK_TYPE_DISALLOWED: "Rank type not accepted",
    Unmet.RANK_SCREENSHOT_MISSING: "Rank screenshot missing",
    Unmet.BATTLECUP_SCREENSHOT_MISSING: "Battle Cup screenshot missing",
    Unmet.BELOW_MIN_MMR: "Below minimum MMR",
}

_PROFILE_ATTRS = ("dota_profile", "deadlock_profile")
_RANK_STATUSES = ("active", "previous", "never")


def steam_friend_id_from_profiles(org_user: OrgUser | None) -> str:
    """Friend ID from the Dota profile, else the Deadlock one; ``""`` if none.

    One Steam account backs both games, so either profile identifies it.
    """
    if org_user is None:
        return ""
    for attr in _PROFILE_ATTRS:
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        if value:
            return value
    return ""


def has_steam_id(user: CustomUser, org_user: OrgUser | None) -> bool:
    """True for a linked Steam account or a numeric profile friend ID that
    no other user owns as ``steam_account_id``."""
    if user.steamid:
        return True
    fid = steam_friend_id_from_profiles(org_user).strip()
    if not (fid.isascii() and fid.isdigit()):
        return False
    account_id = int(fid)
    if account_id > STEAM_ACCOUNT_ID_MAX:
        return True
    return (
        not CustomUser.objects.filter(steam_account_id=account_id)
        .exclude(pk=user.pk)
        .exists()
    )


class GameRequirements(Protocol):
    def mmr_verified(self, org_user: OrgUser | None) -> bool: ...

    def unmet(
        self, event: Event, user: CustomUser, org_user: OrgUser | None
    ) -> list[Unmet]: ...


class DotaRequirements:
    def mmr_verified(self, org_user: OrgUser | None) -> bool:
        return bool(org_user and org_user.has_active_dota_mmr)

    def unmet(
        self, event: Event, user: CustomUser, org_user: OrgUser | None
    ) -> list[Unmet]:
        profile = (
            PlayerDotaProfile.objects.filter(org_user=org_user).first()
            if org_user is not None
            else None
        )
        if profile is None or profile.rank_declared_at is None:
            # Fail closed when any gate would reject some undeclared answer.
            probes = (PlayerDotaProfile(rank_status=s) for s in _RANK_STATUSES)
            if any(self._rank_codes(event, p) for p in probes):
                return [Unmet.DOTA_RANK_UNDECLARED]
            return []
        return self._rank_codes(event, profile)

    def _rank_codes(self, event: Event, profile: PlayerDotaProfile) -> list[Unmet]:
        """``min_mmr`` applies to active ranks only: previous and never-ranked
        players have no current MMR and are judged by ``allow_*`` instead."""
        cfg = DotaModalConfig.from_event(event)
        status = profile.rank_status
        allowed = {
            "active": cfg.allow_active_mmr,
            "previous": cfg.allow_previous_rank,
            "never": cfg.allow_battlecup_rating,
        }
        codes: list[Unmet] = []
        if not allowed.get(status, True):
            codes.append(Unmet.RANK_TYPE_DISALLOWED)
        if dota_require_screenshot(status, cfg):
            if status == "active" and not profile.rank_screenshot:
                codes.append(Unmet.RANK_SCREENSHOT_MISSING)
            if status == "never" and not profile.battlecup_screenshot:
                codes.append(Unmet.BATTLECUP_SCREENSHOT_MISSING)
        if cfg.min_mmr and status == "active":
            if not profile.mmr or profile.mmr < cfg.min_mmr:
                codes.append(Unmet.BELOW_MIN_MMR)
        return codes


class DeadlockRequirements:
    def mmr_verified(self, org_user: OrgUser | None) -> bool:
        return True

    def unmet(
        self, event: Event, user: CustomUser, org_user: OrgUser | None
    ) -> list[Unmet]:
        return []


REQUIREMENT_CHECKS: dict[GameType, GameRequirements] = {
    GameType.DOTA2: DotaRequirements(),
    GameType.DEADLOCK: DeadlockRequirements(),
}


def _org_user_for(event: Event, user: CustomUser) -> OrgUser | None:
    if event.organization_id is None:
        return None
    return OrgUser.objects.filter(
        user=user, organization_id=event.organization_id
    ).first()


def unmet_requirements(event: Event, user: CustomUser) -> list[Unmet]:
    """Codes for every requirement ``user`` misses; empty means eligible."""
    org_user = _org_user_for(event, user)
    game = REQUIREMENT_CHECKS[GameType(event.game_type)]
    codes: list[Unmet] = []
    if event.require_steam_id and not has_steam_id(user, org_user):
        codes.append(Unmet.STEAM_ID_MISSING)
    if event.require_mmr_verified and not game.mmr_verified(org_user):
        codes.append(Unmet.MMR_UNVERIFIED)
    if event.require_profile_complete and not (
        user.nickname and has_steam_id(user, org_user) and user.discordId
    ):
        codes.append(Unmet.PROFILE_INCOMPLETE)
    codes.extend(game.unmet(event, user, org_user))
    return list(dict.fromkeys(codes))
