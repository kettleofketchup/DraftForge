"""Shared staff override contract (#585)."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from rest_framework import serializers

from org.settings_constants import ALL_CODES, StaffOverridePolicy
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from org.models import OrgSettings

log = get_logger(__name__)

ViolationCategory = Literal["seating", "eligibility", "team"]

REASON_MAX_LENGTH: int = 500
OVERRIDE_REQUIRED_CODE: str = "override_required"
OVERRIDE_REASON_REQUIRED_CODE: str = "override_reason_required"
STAFF_REASON_REQUIRED_CODE: str = "reason_required"

_ALL_CODES: frozenset[str] = frozenset(ALL_CODES)


@dataclass(frozen=True)
class Violation:
    code: str
    rule: str
    message: str
    category: ViolationCategory
    blocking: bool = False
    params: dict[str, object] = field(default_factory=dict, hash=False)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class OverrideRequired(Exception):
    def __init__(self, violations: list[Violation], *, blocked: bool = False) -> None:
        super().__init__(", ".join(v.code for v in violations))
        self.violations: list[Violation] = violations
        self.blocked: bool = blocked or any(v.blocking for v in violations)

    def as_response_data(self) -> dict[str, object]:
        return {
            "code": OVERRIDE_REQUIRED_CODE,
            "blocked": self.blocked,
            "violations": [v.as_dict() for v in self.violations],
        }


class OverrideReasonRequired(Exception):
    def __init__(self, message: str = "An override needs a reason.") -> None:
        super().__init__(message)

    def as_response_data(self) -> dict[str, object]:
        return {"code": OVERRIDE_REASON_REQUIRED_CODE}


class StaffReasonRequired(Exception):
    def __init__(self, message: str = "This staff change needs a reason.") -> None:
        super().__init__(message)

    def as_response_data(self) -> dict[str, str]:
        return {"error": STAFF_REASON_REQUIRED_CODE}


@dataclass(frozen=True)
class OverrideResult:
    overridden: list[str]
    prompted: list[str]
    reason: str | None


@dataclass(frozen=True)
class OverrideRequest:
    acknowledged_codes: list[str]
    reason: str


class OverrideRequestSerializer(serializers.Serializer):
    acknowledged_codes = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
        max_length=100,
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
        trim_whitespace=False,
    )


def parse_override_request(data: Mapping[str, Any]) -> OverrideRequest:
    """Read `acknowledged_codes` and `reason` from a request body (400 if malformed)."""
    serializer = OverrideRequestSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return OverrideRequest(
        acknowledged_codes=list(serializer.validated_data["acknowledged_codes"]),
        reason=serializer.validated_data["reason"] or "",
    )


class StaffReasonSerializer(OverrideRequestSerializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
        max_length=REASON_MAX_LENGTH,
        trim_whitespace=True,
    )


def parse_staff_reason(data: Mapping[str, Any]) -> str:
    """Read the trimmed staff `reason` from a request body (400 if malformed)."""
    serializer = StaffReasonSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data["reason"] or ""


def org_override_settings(organization_id: int) -> OrgSettings:
    """The organization's settings row that ``check_overrides`` reads its policy from."""
    # Deferred: this module must import no models (test_module_loads_no_models).
    from org.settings_service import get_org_settings

    return get_org_settings(organization_id)


def _policy(org_settings: OrgSettings | None) -> str:
    if org_settings is None:
        return StaffOverridePolicy.SILENT
    return org_settings.staff_override_policy


def _warning_codes(org_settings: OrgSettings | None) -> frozenset[str]:
    if org_settings is None:
        return _ALL_CODES
    return frozenset(org_settings.staff_override_warning_codes)


def _unique(codes: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(codes))


def notify_override_blocked(
    violations: Sequence[Violation], *, org_settings: OrgSettings | None
) -> None:
    # TODO(#561): emit an operations notice through the #536 registry.
    log.info(
        "override_blocked",
        system="events",
        subsystem="overrides",
        organization_id=getattr(org_settings, "organization_id", None),
        codes=[v.code for v in violations],
        blocking=[v.code for v in violations if v.blocking],
    )


def resolve_overrides(
    violations: Sequence[Violation],
    *,
    org_settings: OrgSettings | None,
    acknowledged: Collection[str],
    reason: str | None,
) -> OverrideResult:
    """Apply the org's policy; raise OverrideRequired / OverrideReasonRequired."""
    policy = _policy(org_settings)
    acked = set(acknowledged)
    resolved: list[Violation] = []
    passed: list[Violation] = []
    for violation in violations:
        if violation.code not in _ALL_CODES:
            resolved.append(replace(violation, blocking=False))
        elif policy == StaffOverridePolicy.SILENT or (
            violation.code not in _warning_codes(org_settings)
        ):
            passed.append(replace(violation, blocking=False))
        else:
            resolved.append(
                replace(violation, blocking=policy == StaffOverridePolicy.BLOCK)
            )

    unacknowledged = [v for v in resolved if not v.blocking and v.code not in acked]
    blocked = any(v.blocking for v in resolved)
    log.info(
        "override_checked",
        system="events",
        subsystem="overrides",
        organization_id=getattr(org_settings, "organization_id", None),
        policy=policy,
        codes=[v.code for v in violations],
        passed=[v.code for v in passed],
        prompted=[v.code for v in resolved if not v.blocking],
        blocking=[v.code for v in resolved if v.blocking],
        unacknowledged=[v.code for v in unacknowledged],
    )

    if blocked:
        notify_override_blocked(resolved, org_settings=org_settings)
        raise OverrideRequired(resolved, blocked=True)
    if unacknowledged:
        raise OverrideRequired(unacknowledged)

    trimmed = (reason or "").strip()
    if resolved and not 0 < len(trimmed) <= REASON_MAX_LENGTH:
        raise OverrideReasonRequired()

    return OverrideResult(
        overridden=_unique([v.code for v in violations]),
        prompted=_unique([v.code for v in resolved]),
        reason=trimmed if resolved else None,
    )


def check_overrides(
    violations: Sequence[Violation],
    *,
    org_settings: OrgSettings | None,
    acknowledged: Collection[str],
    reason: str | None,
) -> list[str]:
    """Return the overridden codes; raise OverrideRequired / OverrideReasonRequired."""
    return resolve_overrides(
        violations,
        org_settings=org_settings,
        acknowledged=acknowledged,
        reason=reason,
    ).overridden
