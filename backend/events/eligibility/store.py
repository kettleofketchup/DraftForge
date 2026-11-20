"""Persisting evaluation results on signups."""

from __future__ import annotations

import datetime
from typing import Any

from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from events.constants import UNMET_TRACKED_STATUSES
from events.eligibility.evaluate import evaluate_signup
from events.eligibility.reasons import EligibilityResult
from events.models import EventSignup
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


def refresh_unmet_requirements(org_user: OrgUser) -> int:
    """Recompute stored reasons on the user's open signups in the org; the
    status is not re-decided. Every writer of a requirement input (game
    profiles, MMR verification) calls this after saving. Returns the number
    of rows changed."""
    signups = (
        EventSignup.objects.nocache()
        .filter(
            user_id=org_user.user_id,
            event__organization_id=org_user.organization_id,
            status__in=UNMET_TRACKED_STATUSES,
        )
        .select_related("event", "user")
    )
    changed: list[EventSignup] = []
    for signup in signups:
        result = evaluate_signup(signup.event, signup.user)
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
