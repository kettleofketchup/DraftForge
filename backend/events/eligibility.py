"""Which signup requirements a user does not meet for an event.

Generic requirements apply to every game; game-specific ones come from
``REQUIREMENT_CHECKS`` keyed by ``event.game_type``. Add a game by
registering a ``GameRequirements`` implementation there.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, GameType, Organization
from events.models import Event
from events.schemas import DotaModalConfig, dota_require_screenshot
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile
from telemetry.logging import get_logger

log = get_logger(__name__)

# Steam account IDs are unsigned 32-bit; 0 is never assigned.
STEAM_ACCOUNT_ID_RANGE = range(1, 2**32)
# Range of the CustomUser.steam_account_id IntegerField.
STORED_STEAM_ACCOUNT_ID_MAX = 2**31 - 1
FRIEND_ID_MAX_LENGTH = 20


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


def steam_friend_id_from_profiles(org_user: OrgUser | None) -> str:
    """First numeric friend ID across the game profiles; ``""`` if none.

    One Steam account backs both games, so either profile identifies it.
    """
    if org_user is None:
        return ""
    for attr in _PROFILE_ATTRS:
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        value = (value or "").strip()
        if value.isascii() and value.isdigit():
            return value
    return ""


def _raw_friend_id_from_profiles(org_user: OrgUser) -> str:
    for attr in _PROFILE_ATTRS:
        value = getattr(getattr(org_user, attr, None), "unverified_friend_id", "")
        if (value or "").strip():
            return value.strip()
    return ""


def sync_steam_account_from_profiles(
    user: CustomUser, org: Organization | None, *, event_id: int | None = None
) -> bool:
    """Copy the profile friend ID onto an empty ``user.steam_account_id``.

    Never raises for bad data: a conflict, out-of-range or non-numeric ID is
    logged, ``user`` is reloaded, and False is returned. True when it wrote.
    """
    if org is None or user.steam_account_id:
        return False
    org_user = OrgUser.objects.filter(user=user, organization=org).first()
    if org_user is None:
        return False
    fid = steam_friend_id_from_profiles(org_user)
    if not fid:
        if _raw_friend_id_from_profiles(org_user):
            _log_writethrough_skipped(user, event_id, reason="non_numeric")
        return False
    account_id = int(fid)
    if account_id not in STEAM_ACCOUNT_ID_RANGE or (
        account_id > STORED_STEAM_ACCOUNT_ID_MAX
    ):
        _log_writethrough_skipped(user, event_id, reason="out_of_range")
        return False
    try:
        with transaction.atomic():
            user.steam_account_id = account_id
            user.save(update_fields=["steam_account_id", "steamid"])
    except IntegrityError:
        user.refresh_from_db(fields=["steam_account_id", "steamid"])
        conflicting_user_id = (
            CustomUser.objects.filter(steam_account_id=account_id)
            .exclude(pk=user.pk)
            .values_list("pk", flat=True)
            .first()
        )
        _log_writethrough_skipped(
            user,
            event_id,
            reason="conflict",
            conflicting_user_id=conflicting_user_id,
        )
        return False
    invalidate_after_commit(user)
    return True


def _log_writethrough_skipped(
    user: CustomUser,
    event_id: int | None,
    *,
    reason: str,
    conflicting_user_id: int | None = None,
) -> None:
    log.warning(
        "signup_steam_writethrough_skipped",
        system="events",
        subsystem="services",
        tags=["events", "signup"],
        tags_csv="events,signup",
        reason=reason,
        user_id=user.pk,
        event_id=event_id,
        conflicting_user_id=conflicting_user_id,
    )


def validate_friend_id(fid: str, org_user: OrgUser) -> str:
    """Return ``fid`` in canonical form (stripped, no leading zeros), or
    raise if it is malformed or owned by another account (any game profile,
    or another user's Steam account).

    ``""`` is returned as-is so callers can clear the field.
    """
    fid = fid.strip()
    if not fid:
        return fid
    if not (fid.isascii() and fid.isdigit()) or len(fid) > FRIEND_ID_MAX_LENGTH:
        raise ValidationError(
            f"Friend ID must be digits only (max {FRIEND_ID_MAX_LENGTH}).",
            code="invalid_friend_id",
        )
    fid = str(int(fid))
    # Global scope: Friend ID is unique site-wide, not per-org.
    collision = any(
        model.objects.filter(unverified_friend_id=fid)
        .exclude(org_user=org_user)
        .exists()
        for model in (PlayerDotaProfile, PlayerDeadlockProfile)
    )
    account_id = int(fid)
    if not collision and account_id <= STORED_STEAM_ACCOUNT_ID_MAX:
        collision = (
            CustomUser.objects.filter(steam_account_id=account_id)
            .exclude(pk=org_user.user_id)
            .exists()
        )
    if collision:
        raise ValidationError(
            f"Friend ID {fid} is already registered to another account. "
            f"Contact an admin or login to {settings.SITE_URL} to claim it.",
            code="duplicate_friend_id",
        )
    return fid


def has_steam_id(user: CustomUser, org_user: OrgUser | None) -> bool:
    """True for a linked Steam account or a numeric profile friend ID that
    no other user owns as ``steam_account_id``."""
    if user.steamid:
        return True
    fid = steam_friend_id_from_profiles(org_user)
    if not fid:
        return False
    account_id = int(fid)
    if account_id not in STEAM_ACCOUNT_ID_RANGE:
        return False
    if account_id > STORED_STEAM_ACCOUNT_ID_MAX:
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
        profile: PlayerDotaProfile | None = getattr(org_user, "dota_profile", None)
        if profile is None or not profile.is_rank_declared:
            # Fail closed when any gate would reject some undeclared answer.
            probes = (
                PlayerDotaProfile(rank_status=s)
                for s in PlayerDotaProfile.RANK_STATUSES
            )
            if any(self._rank_codes(event, p) for p in probes):
                return [Unmet.DOTA_RANK_UNDECLARED]
            return []
        return self._rank_codes(event, profile)

    def _rank_codes(self, event: Event, profile: PlayerDotaProfile) -> list[Unmet]:
        """``min_mmr`` applies to active ranks only: previous and never-ranked
        players have no current MMR and are judged by ``allow_*`` instead."""
        cfg = DotaModalConfig.from_event(event)
        status = profile.rank_status
        codes: list[Unmet] = []
        if not cfg.allows_rank_status(status):
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
    steam_ok = (
        has_steam_id(user, org_user)
        if event.require_steam_id or event.require_profile_complete
        else True
    )
    codes: list[Unmet] = []
    if event.require_steam_id and not steam_ok:
        codes.append(Unmet.STEAM_ID_MISSING)
    if event.require_mmr_verified and not game.mmr_verified(org_user):
        codes.append(Unmet.MMR_UNVERIFIED)
    if event.require_profile_complete and not (
        user.nickname and steam_ok and user.discordId
    ):
        codes.append(Unmet.PROFILE_INCOMPLETE)
    codes.extend(game.unmet(event, user, org_user))
    return list(dict.fromkeys(codes))
