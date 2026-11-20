"""Value types returned by the eligibility evaluator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from django.db import models


class ReasonCode(models.TextChoices):
    """Stable codes; the values are stored on signups and read by the clients."""

    STEAM_ID_MISSING = "steam_id_missing", "Steam friend ID missing"
    MMR_UNVERIFIED = "mmr_unverified", "MMR not verified"
    PROFILE_INCOMPLETE = "profile_incomplete", "Profile incomplete"
    DOTA_RANK_UNDECLARED = "dota_rank_undeclared", "Rank not declared"
    RANK_TYPE_DISALLOWED = "rank_type_disallowed", "Rank type not accepted"
    RANK_SCREENSHOT_MISSING = "rank_screenshot_missing", "Rank screenshot missing"
    BATTLECUP_SCREENSHOT_MISSING = (
        "battlecup_screenshot_missing",
        "Battle Cup screenshot missing",
    )
    BELOW_MIN_MMR = "below_min_mmr", "Below minimum MMR"
    CONDUCT_BELOW_THRESHOLD = (
        "conduct_below_threshold",
        "Attendance record below org threshold",
    )


class Severity(models.TextChoices):
    BLOCK = "block", "Block"
    NEEDS_APPROVAL = "needs_approval", "Needs approval"


class FixKind(models.TextChoices):
    UPDATE_PROFILE = "update_profile", "Update profile"


class Rule:
    """Slugs naming the rule each reason enforces."""

    REQUIRE_STEAM_ID: Final = "require-steam-id"
    REQUIRE_MMR_VERIFIED: Final = "require-mmr-verified"
    REQUIRE_PROFILE_COMPLETE: Final = "require-profile-complete"
    DOTA_RANK_DECLARED: Final = "dota-rank-declared"
    DOTA_RANK_TYPE: Final = "dota-rank-type"
    DOTA_RANK_SCREENSHOT: Final = "dota-rank-screenshot"
    DOTA_BATTLECUP_SCREENSHOT: Final = "dota-battlecup-screenshot"
    DOTA_MIN_MMR: Final = "dota-min-mmr"
    ORG_CONDUCT_THRESHOLD: Final = "org-conduct-threshold"


@dataclass(frozen=True, slots=True)
class FixAction:
    kind: FixKind
    url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": str(self.kind), "url": self.url}


@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    severity: Severity
    rule: str
    message: str
    fix: FixAction | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "severity": str(self.severity),
            "rule": self.rule,
            "message": self.message,
            "fix": self.fix.as_dict() if self.fix else None,
            "params": dict(self.params),
        }


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    reasons: tuple[Reason, ...] = ()

    @property
    def blocking(self) -> tuple[Reason, ...]:
        return tuple(r for r in self.reasons if r.severity == Severity.BLOCK)

    @property
    def approval(self) -> tuple[Reason, ...]:
        return tuple(r for r in self.reasons if r.severity == Severity.NEEDS_APPROVAL)

    @property
    def admissible(self) -> bool:
        return not self.blocking

    @property
    def clean(self) -> bool:
        return not self.reasons

    @property
    def codes(self) -> list[str]:
        return [str(r.code) for r in self.reasons]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [r.as_dict() for r in self.reasons]
