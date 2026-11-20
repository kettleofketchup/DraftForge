"""Which signup requirements a user does not meet for an event.

Generic requirements apply to every game; game-specific ones come from
``REQUIREMENT_CHECKS`` keyed by ``event.game_type``. Add a game by
registering a ``GameRequirements`` implementation there.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, GameType, Organization
from events.constants import UNMET_TRACKED_STATUSES, EventState
from events.models import Event, EventSignup
from events.schemas import DotaModalConfig, dota_require_screenshot
from org.conduct.constants import Tier
from org.conduct.enforcement import tier_for, tiers_for
from org.conduct.gate import ConductGate, conduct_gate
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
    CONDUCT_BELOW_THRESHOLD = "conduct_below_threshold"


UNMET_LABELS: dict[Unmet, str] = {
    Unmet.STEAM_ID_MISSING: "Steam friend ID missing",
    Unmet.MMR_UNVERIFIED: "MMR not verified",
    Unmet.PROFILE_INCOMPLETE: "Profile incomplete",
    Unmet.DOTA_RANK_UNDECLARED: "Rank not declared",
    Unmet.RANK_TYPE_DISALLOWED: "Rank type not accepted",
    Unmet.RANK_SCREENSHOT_MISSING: "Rank screenshot missing",
    Unmet.BATTLECUP_SCREENSHOT_MISSING: "Battle Cup screenshot missing",
    Unmet.BELOW_MIN_MMR: "Below minimum MMR",
    Unmet.CONDUCT_BELOW_THRESHOLD: "Attendance record below org threshold",
}

_PROFILE_ATTRS = ("dota_profile", "deadlock_profile")


def unmet_labels(codes: Iterable[str]) -> list[str]:
    """Labels for stored codes; an unknown code is shown as-is."""
    return [UNMET_LABELS[Unmet(code)] if code in Unmet else code for code in codes]


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
    raise if it is malformed or owned by another user (any of their game
    profiles in any org, or their Steam account).

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
        .exclude(org_user__user_id=org_user.user_id)
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


_CONDUCT_HOLD_TIERS = frozenset({Tier.REQUIRE_APPROVAL, Tier.BLOCK})
_CLOSED_EVENT_STATES = frozenset({EventState.COMPLETED, EventState.CANCELLED})


def unmet_requirements(
    event: Event,
    user: CustomUser,
    *,
    gate: ConductGate | None = None,
    tier: Tier | None = None,
) -> list[Unmet]:
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
    if tier is None:
        tier = tier_for(gate or conduct_gate(event.organization_id), user)
    if tier in _CONDUCT_HOLD_TIERS:
        codes.append(Unmet.CONDUCT_BELOW_THRESHOLD)
    return list(dict.fromkeys(codes))


def unmet_codes(
    event: Event,
    user: CustomUser,
    *,
    gate: ConductGate | None = None,
    tier: Tier | None = None,
) -> list[str]:
    """``unmet_requirements`` as the string codes stored on a signup."""
    return [
        code.value for code in unmet_requirements(event, user, gate=gate, tier=tier)
    ]


def refresh_unmet_requirements(
    org_user: OrgUser, *, gate: ConductGate | None = None
) -> int:
    """Recompute stored ``unmet_requirements`` on the user's open signups in
    the org; the status is not re-decided. Every writer of a requirement
    input (game profiles, MMR verification) calls this after saving.
    Returns the number of rows changed."""
    signups = list(
        EventSignup.objects.nocache()
        .filter(
            user_id=org_user.user_id,
            event__organization_id=org_user.organization_id,
            status__in=UNMET_TRACKED_STATUSES,
        )
        .select_related("event", "user")
    )
    if not signups:
        return 0
    if gate is None:
        gate = conduct_gate(org_user.organization_id)
    tier = tier_for(gate, signups[0].user)
    return _store_unmet_codes(signups, {org_user.user_id: tier})


def refresh_org_unmet_requirements(
    org_id: int, *, gate: ConductGate | None = None
) -> int:
    """``refresh_unmet_requirements`` for every open signup in the org, with
    one conduct score query; run after the org's conduct inputs change."""
    signups = list(
        EventSignup.objects.nocache()
        .filter(
            event__organization_id=org_id,
            status__in=UNMET_TRACKED_STATUSES,
        )
        .exclude(event__state__in=_CLOSED_EVENT_STATES)
        .select_related("event", "user")
    )
    if not signups:
        return 0
    if gate is None:
        gate = conduct_gate(org_id)
    users = {signup.user_id: signup.user for signup in signups}
    return _store_unmet_codes(signups, tiers_for(gate, users.values()))


def _store_unmet_codes(signups: list[EventSignup], tiers: Mapping[int, Tier]) -> int:
    changed: list[EventSignup] = []
    for signup in signups:
        codes = unmet_codes(
            signup.event, signup.user, tier=tiers.get(signup.user_id, Tier.OK)
        )
        if codes == signup.unmet_requirements:
            continue
        signup.unmet_requirements = codes
        signup.save(update_fields=["unmet_requirements"])
        changed.append(signup)
    if changed:
        events = {signup.event_id: signup.event for signup in changed}
        invalidate_after_commit(*changed, *events.values())
    return len(changed)
