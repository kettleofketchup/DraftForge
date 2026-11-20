"""Persisting evaluation results on signups."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any

from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from events.constants import UNMET_TRACKED_STATUSES, EventState
from events.eligibility.checks.conduct import prime_conduct
from events.eligibility.evaluate import evaluate_signup
from events.eligibility.reasons import EligibilityResult
from events.models import EventSignup
from org.models import OrgUser
from org.standing import restamp
from org.standing.cache import StandingCache

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


_CLOSED_EVENT_STATES: frozenset[str] = frozenset(
    {EventState.COMPLETED, EventState.CANCELLED}
)


def recheck_signup(signup: EventSignup) -> EventSignup:
    """Re-evaluate and store the signup's reasons; the status is not re-decided."""
    result = evaluate_signup(signup.event, signup.user, for_staff_placement=True)
    fields = stamp_eligibility(signup, result)
    signup.save(update_fields=[*fields, "updated_at"])
    invalidate_after_commit(signup, signup.event)
    return signup


def refresh_unmet_requirements(org_user: OrgUser) -> int:
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
    return _store_reasons(signups, org_user.organization_id)


def refresh_members_eligibility(org_users: Sequence[OrgUser]) -> int:
    return sum(refresh_unmet_requirements(org_user) for org_user in org_users)


def refresh_org_eligibility(org_id: int) -> int:
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
    return _store_reasons(signups, org_id)


def _store_reasons(signups: Sequence[EventSignup], org_id: int) -> int:
    if not signups:
        return 0
    now = timezone.now()
    cache = StandingCache()
    prime_conduct(org_id, (s.user_id for s in signups), now=now, cache=cache)
    changed: list[EventSignup] = []
    for signup in signups:
        result = evaluate_signup(
            signup.event,
            signup.user,
            now=now,
            for_staff_placement=True,
            standing_cache=cache,
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


restamp.register(refresh_org_eligibility, refresh_members_eligibility)
