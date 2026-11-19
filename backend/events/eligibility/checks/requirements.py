"""The event's ``require_*`` settings and the per-game rank gates.

Every failure needs staff approval. Add a game by registering a
``GameRequirements`` implementation in ``REQUIREMENT_CHECKS``.
"""

from __future__ import annotations

from typing import Any, Protocol

from django.conf import settings

from app.models import GameType
from events.eligibility.context import EvalContext
from events.eligibility.gating import has_registered_steam_id
from events.eligibility.reasons import (
    FixAction,
    FixKind,
    Reason,
    ReasonCode,
    Rule,
    Severity,
)
from events.models import Event
from events.schemas import DotaModalConfig, dota_require_screenshot
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile

MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.STEAM_ID_MISSING: "This event requires a Steam friend ID on your profile.",
    ReasonCode.MMR_UNVERIFIED: "This event requires staff-verified MMR.",
    ReasonCode.PROFILE_INCOMPLETE: (
        "This event requires a complete profile: nickname, Steam ID and Discord."
    ),
    ReasonCode.DOTA_RANK_UNDECLARED: "Declare your rank to sign up for this event.",
    ReasonCode.RANK_TYPE_DISALLOWED: "This event does not accept your rank type.",
    ReasonCode.RANK_SCREENSHOT_MISSING: "This event requires a rank screenshot.",
    ReasonCode.BATTLECUP_SCREENSHOT_MISSING: (
        "This event requires a Battle Cup screenshot."
    ),
    ReasonCode.BELOW_MIN_MMR: "Your MMR is below this event's minimum.",
}

RULES: dict[ReasonCode, str] = {
    ReasonCode.STEAM_ID_MISSING: Rule.REQUIRE_STEAM_ID,
    ReasonCode.MMR_UNVERIFIED: Rule.REQUIRE_MMR_VERIFIED,
    ReasonCode.PROFILE_INCOMPLETE: Rule.REQUIRE_PROFILE_COMPLETE,
    ReasonCode.DOTA_RANK_UNDECLARED: Rule.DOTA_RANK_DECLARED,
    ReasonCode.RANK_TYPE_DISALLOWED: Rule.DOTA_RANK_TYPE,
    ReasonCode.RANK_SCREENSHOT_MISSING: Rule.DOTA_RANK_SCREENSHOT,
    ReasonCode.BATTLECUP_SCREENSHOT_MISSING: Rule.DOTA_BATTLECUP_SCREENSHOT,
    ReasonCode.BELOW_MIN_MMR: Rule.DOTA_MIN_MMR,
}

_PROFILE_FIXABLE: frozenset[ReasonCode] = frozenset(
    {ReasonCode.STEAM_ID_MISSING, ReasonCode.PROFILE_INCOMPLETE}
)


def profile_url() -> str:
    return f"{settings.SITE_URL}/profile"


def requirement_reason(code: ReasonCode, **params: Any) -> Reason:
    fix = (
        FixAction(FixKind.UPDATE_PROFILE, url=profile_url())
        if code in _PROFILE_FIXABLE
        else None
    )
    return Reason(
        code=code,
        severity=Severity.NEEDS_APPROVAL,
        rule=RULES[code],
        message=MESSAGES[code],
        fix=fix,
        params=params,
    )


class GameRequirements(Protocol):
    def mmr_verified(self, org_user: OrgUser | None) -> bool: ...

    def reasons(self, ctx: EvalContext) -> list[Reason]: ...


class DotaRequirements:
    def mmr_verified(self, org_user: OrgUser | None) -> bool:
        return bool(org_user and org_user.has_active_dota_mmr)

    def reasons(self, ctx: EvalContext) -> list[Reason]:
        profile = ctx.dota_profile
        if profile is None or not profile.is_rank_declared:
            # Fail closed when any gate would reject some undeclared answer.
            probes = (
                PlayerDotaProfile(rank_status=s)
                for s in PlayerDotaProfile.RANK_STATUSES
            )
            if any(self._rank_reasons(ctx.event, p) for p in probes):
                return [requirement_reason(ReasonCode.DOTA_RANK_UNDECLARED)]
            return []
        return self._rank_reasons(ctx.event, profile)

    def _rank_reasons(self, event: Event, profile: PlayerDotaProfile) -> list[Reason]:
        """``min_mmr`` applies to active ranks only: previous and never-ranked
        players have no current MMR and are judged by ``allow_*`` instead."""
        cfg = DotaModalConfig.from_event(event)
        status = profile.rank_status
        reasons: list[Reason] = []
        if not cfg.allows_rank_status(status):
            reasons.append(
                requirement_reason(ReasonCode.RANK_TYPE_DISALLOWED, rank_status=status)
            )
        if dota_require_screenshot(status, cfg):
            if status == "active" and not profile.rank_screenshot:
                reasons.append(requirement_reason(ReasonCode.RANK_SCREENSHOT_MISSING))
            if status == "never" and not profile.battlecup_screenshot:
                reasons.append(
                    requirement_reason(ReasonCode.BATTLECUP_SCREENSHOT_MISSING)
                )
        if cfg.min_mmr and status == "active":
            if not profile.mmr or profile.mmr < cfg.min_mmr:
                reasons.append(
                    requirement_reason(
                        ReasonCode.BELOW_MIN_MMR,
                        min_mmr=cfg.min_mmr,
                        mmr=profile.mmr,
                    )
                )
        return reasons


class DeadlockRequirements:
    def mmr_verified(self, org_user: OrgUser | None) -> bool:
        return True

    def reasons(self, ctx: EvalContext) -> list[Reason]:
        return []


REQUIREMENT_CHECKS: dict[GameType, GameRequirements] = {
    GameType.DOTA2: DotaRequirements(),
    GameType.DEADLOCK: DeadlockRequirements(),
}


def check_event_requirements(ctx: EvalContext) -> list[Reason]:
    event, user, org_user = ctx.event, ctx.user, ctx.org_user
    game = REQUIREMENT_CHECKS[GameType(event.game_type)]
    steam_ok = (
        has_registered_steam_id(user, org_user)
        if event.require_steam_id or event.require_profile_complete
        else True
    )
    reasons: list[Reason] = []
    if event.require_steam_id and not steam_ok:
        reasons.append(requirement_reason(ReasonCode.STEAM_ID_MISSING))
    if event.require_mmr_verified and not game.mmr_verified(org_user):
        reasons.append(requirement_reason(ReasonCode.MMR_UNVERIFIED))
    if event.require_profile_complete and not (
        user.nickname and steam_ok and user.discordId
    ):
        reasons.append(requirement_reason(ReasonCode.PROFILE_INCOMPLETE))
    reasons.extend(game.reasons(ctx))
    return reasons
