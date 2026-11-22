"""Signup eligibility: an ordered registry of checks returning structured
reasons, plus the Steam ID helpers they share."""

from collections.abc import Iterable

from events.eligibility.checks.requirements import (
    REQUIREMENT_CHECKS,
    DeadlockRequirements,
    DotaRequirements,
    GameRequirements,
)
from events.eligibility.context import EvalContext
from events.eligibility.evaluate import (
    CHECKS,
    evaluate_signup,
    unmet_codes,
    unmet_requirements,
)
from events.eligibility.gating import (
    GatedMetric,
    gated_metrics,
    has_registered_steam_id,
    is_skill_gated,
)
from events.eligibility.reasons import (
    EligibilityResult,
    FixAction,
    FixKind,
    Reason,
    ReasonCode,
    Rule,
    Severity,
)
from events.eligibility.steam import (
    FRIEND_ID_MAX_LENGTH,
    STEAM_ACCOUNT_ID_RANGE,
    claim_friend_id,
    precheck_friend_id,
    validate_friend_id,
)
from events.eligibility.store import (
    clear_eligibility,
    eligibility_values,
    recheck_signup,
    refresh_members_eligibility,
    refresh_org_eligibility,
    refresh_unmet_requirements,
    stamp_eligibility,
)

Unmet = ReasonCode
UNMET_LABELS: dict[ReasonCode, str] = {code: code.label for code in ReasonCode}
has_steam_id = has_registered_steam_id


def unmet_labels(codes: Iterable[str]) -> list[str]:
    """Labels for stored codes; an unknown code is shown as-is."""
    return [UNMET_LABELS[Unmet(code)] if code in Unmet else code for code in codes]


__all__ = [
    "CHECKS",
    "FRIEND_ID_MAX_LENGTH",
    "REQUIREMENT_CHECKS",
    "STEAM_ACCOUNT_ID_RANGE",
    "UNMET_LABELS",
    "DeadlockRequirements",
    "DotaRequirements",
    "EligibilityResult",
    "EvalContext",
    "FixAction",
    "FixKind",
    "GameRequirements",
    "GatedMetric",
    "Reason",
    "ReasonCode",
    "Rule",
    "Severity",
    "Unmet",
    "claim_friend_id",
    "clear_eligibility",
    "eligibility_values",
    "evaluate_signup",
    "gated_metrics",
    "has_registered_steam_id",
    "has_steam_id",
    "is_skill_gated",
    "precheck_friend_id",
    "recheck_signup",
    "refresh_members_eligibility",
    "refresh_org_eligibility",
    "refresh_unmet_requirements",
    "stamp_eligibility",
    "unmet_codes",
    "unmet_labels",
    "unmet_requirements",
    "validate_friend_id",
]
