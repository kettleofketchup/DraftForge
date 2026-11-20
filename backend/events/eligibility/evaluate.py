from __future__ import annotations

import datetime
from collections.abc import Callable, Collection

from django.utils import timezone

from app.models import CustomUser
from events.constants import Commitment
from events.eligibility.checks.conduct import check_conduct
from events.eligibility.checks.requirements import check_event_requirements
from events.eligibility.context import EvalContext
from events.eligibility.reasons import EligibilityResult, Reason, ReasonCode
from events.models import Event
from org.conduct.constants import Tier
from org.conduct.gate import ConductGate
from telemetry.logging import get_logger

log = get_logger(__name__)

Check = Callable[[EvalContext], list[Reason]]

# Run in order; a later check never repeats a code an earlier one reported.
CHECKS: tuple[Check, ...] = (check_event_requirements, check_conduct)


def evaluate_signup(
    event: Event,
    user: CustomUser,
    *,
    intent: Commitment | str = Commitment.MAIN,
    actor: CustomUser | None = None,
    now: datetime.datetime | None = None,
    discord_role_ids: Collection[str] | None = None,
    for_staff_placement: bool = False,
    conduct_gate: ConductGate | None = None,
    conduct_tier: Tier | None = None,
) -> EligibilityResult:
    ctx = EvalContext.load(
        event,
        user,
        intent=Commitment(intent),
        now=now or timezone.now(),
        actor=actor,
        discord_role_ids=discord_role_ids,
        for_staff_placement=for_staff_placement,
        conduct_gate=conduct_gate,
        conduct_tier=conduct_tier,
    )
    seen: set[ReasonCode] = set()
    reasons: list[Reason] = []
    for check in CHECKS:
        for reason in check(ctx):
            if reason.code not in seen:
                seen.add(reason.code)
                reasons.append(reason)
    result = EligibilityResult(tuple(reasons))
    log.info(
        "eligibility_evaluated",
        system="events",
        subsystem="eligibility",
        event_id=event.pk,
        user_id=user.pk,
        intent=str(ctx.intent),
        codes=result.codes,
        admissible=result.admissible,
    )
    return result


def unmet_requirements(
    event: Event,
    user: CustomUser,
    *,
    gate: ConductGate | None = None,
    tier: Tier | None = None,
) -> list[ReasonCode]:
    """Codes for every requirement ``user`` misses; empty means eligible."""
    result = evaluate_signup(event, user, conduct_gate=gate, conduct_tier=tier)
    return [r.code for r in result.reasons]


def unmet_codes(
    event: Event,
    user: CustomUser,
    *,
    gate: ConductGate | None = None,
    tier: Tier | None = None,
) -> list[str]:
    """``unmet_requirements`` as the string codes stored on a signup."""
    return evaluate_signup(event, user, conduct_gate=gate, conduct_tier=tier).codes
