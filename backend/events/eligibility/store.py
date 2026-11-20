"""Persisting evaluation results on signups."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any

from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from events.constants import UNMET_TRACKED_STATUSES, EventState
from events.eligibility.evaluate import evaluate_signup
from events.eligibility.reasons import EligibilityResult
from events.models import EventSignup
from org.conduct.constants import Tier
from org.conduct.enforcement import tier_for, tiers_for
from org.conduct.gate import ConductGate, conduct_gate
from org.models import OrgUser

ELIGIBILITY_FIELDS: tuple[str, ...] = (
    "unmet_requirements",
    "eligibility_reasons",
    "eligibility_checked_at",
)


def eligibility_values(
    result: EligibilityResult, now: datetime.datetime | None = None
) -> dict[str, Any]:
    """``EventSignup`` field values recording ``result``."""
    return {
        "unmet_requirements": result.codes,
        "eligibility_reasons": result.as_dicts(),
        "eligibility_checked_at": now or timezone.now(),
    }


def stamp_eligibility(
    signup: EventSignup,
    result: EligibilityResult,
    now: datetime.datetime | None = None,
) -> list[str]:
    """Write ``result`` onto ``signup`` (unsaved); returns the fields set."""
    values = eligibility_values(result, now)
    for name, value in values.items():
        setattr(signup, name, value)
    return list(values)


def clear_eligibility(signup: EventSignup) -> list[str]:
    """Drop stored reasons (unsaved); returns the fields set."""
    signup.unmet_requirements = []
    signup.eligibility_reasons = []
    signup.eligibility_checked_at = None
    return list(ELIGIBILITY_FIELDS)


def recheck_signup(signup: EventSignup) -> EventSignup:
    """Re-evaluate and store the signup's reasons; the status is not re-decided."""
    fields = stamp_eligibility(signup, evaluate_signup(signup.event, signup.user))
    signup.save(update_fields=[*fields, "updated_at"])
    invalidate_after_commit(signup, signup.event)
    return signup


_CLOSED_EVENT_STATES = frozenset({EventState.COMPLETED, EventState.CANCELLED})


def refresh_unmet_requirements(
    org_user: OrgUser, *, gate: ConductGate | None = None
) -> int:
    """Recompute stored reasons on the user's open signups in the org; the
    status is not re-decided. Every writer of a requirement input (game
    profiles, MMR verification) calls this after saving. Returns the number
    of rows changed."""
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
    return _store_reasons(signups, {org_user.user_id: tier})


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
    return _store_reasons(signups, tiers_for(gate, users.values()))


def _store_reasons(signups: list[EventSignup], tiers: Mapping[int, Tier]) -> int:
    changed: list[EventSignup] = []
    for signup in signups:
        result = evaluate_signup(
            signup.event,
            signup.user,
            conduct_tier=tiers.get(signup.user_id, Tier.OK),
        )
        if (
            result.codes == signup.unmet_requirements
            and result.as_dicts() == signup.eligibility_reasons
        ):
            continue
        signup.save(update_fields=stamp_eligibility(signup, result))
        changed.append(signup)
    if changed:
        events = {signup.event_id: signup.event for signup in changed}
        invalidate_after_commit(*changed, *events.values())
    return len(changed)
