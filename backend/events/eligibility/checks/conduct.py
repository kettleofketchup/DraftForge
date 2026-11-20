"""The org's conduct enforcement: members below the require-approval
threshold are held for staff; below the block threshold they may not sign
themselves up (staff placements are held instead)."""

from __future__ import annotations

import datetime
from collections.abc import Iterable

from events.eligibility.context import EvalContext
from events.eligibility.reasons import Reason, ReasonCode, Rule, Severity
from org.conduct.eligibility import (
    CONDUCT_BLOCK_MESSAGE,
    Tier,
    conduct_tier,
    standings,
)
from org.standing.cache import StandingCache

HOLD_MESSAGE = "Your attendance record is below this organization's threshold."


def _reason(severity: Severity, rule: str, tier: Tier, message: str) -> Reason:
    return Reason(
        code=ReasonCode.CONDUCT_BELOW_THRESHOLD,
        severity=severity,
        rule=rule,
        message=message,
        params={"tier": tier.value},
    )


def check_conduct(ctx: EvalContext) -> list[Reason]:
    if ctx.org_user is None:
        return []
    tier = conduct_tier(
        ctx.event.organization_id,
        ctx.org_user,
        now=ctx.now,
        cache=ctx.standing_cache,
    )
    if tier is Tier.REQUIRE_APPROVAL:
        return [
            _reason(
                Severity.NEEDS_APPROVAL,
                Rule.CONDUCT_REQUIRE_APPROVAL,
                tier,
                HOLD_MESSAGE,
            )
        ]
    if tier is Tier.BLOCK:
        if ctx.for_staff_placement:
            return [
                _reason(Severity.NEEDS_APPROVAL, Rule.CONDUCT_BLOCK, tier, HOLD_MESSAGE)
            ]
        return [
            _reason(Severity.BLOCK, Rule.CONDUCT_BLOCK, tier, CONDUCT_BLOCK_MESSAGE)
        ]
    return []


def prime_conduct(
    org_id: int,
    user_ids: Iterable[int],
    *,
    now: datetime.datetime,
    cache: StandingCache,
) -> None:
    standings(org_id, user_ids, now=now, cache=cache)
