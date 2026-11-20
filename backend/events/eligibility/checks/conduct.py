"""The org's conduct enforcement: members below the require-approval or
block threshold are held for staff. Self sign-up refusal for the block tier
lives in ``events.admission``."""

from __future__ import annotations

from events.eligibility.context import EvalContext
from events.eligibility.reasons import Reason, ReasonCode, Rule, Severity
from org.conduct.constants import Tier
from org.conduct.enforcement import tier_for
from org.conduct.gate import conduct_gate

HOLD_TIERS: frozenset[Tier] = frozenset({Tier.REQUIRE_APPROVAL, Tier.BLOCK})

MESSAGE = "Your attendance record is below this organization's threshold."


def conduct_tier(ctx: EvalContext) -> Tier:
    if ctx.conduct_tier is not None:
        return ctx.conduct_tier
    gate = ctx.conduct_gate or conduct_gate(ctx.event.organization_id)
    return tier_for(gate, ctx.user)


def check_conduct(ctx: EvalContext) -> list[Reason]:
    if conduct_tier(ctx) not in HOLD_TIERS:
        return []
    return [
        Reason(
            code=ReasonCode.CONDUCT_BELOW_THRESHOLD,
            severity=Severity.NEEDS_APPROVAL,
            rule=Rule.ORG_CONDUCT_THRESHOLD,
            message=MESSAGE,
        )
    ]
