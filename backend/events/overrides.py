"""Staff override core: the non-seating slice of #585."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from org.settings_constants import ALL_CODES
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from org.models import OrgSettings

log = get_logger(__name__)

ViolationCategory = Literal["seating", "eligibility", "team"]


@dataclass(frozen=True)
class Violation:
    code: str
    rule: str
    message: str
    category: ViolationCategory

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


class OverrideRequired(Exception):
    def __init__(self, violations: list[Violation], *, blocked: bool = False) -> None:
        super().__init__(", ".join(v.code for v in violations))
        self.violations: list[Violation] = violations
        self.blocked: bool = blocked


class OverrideReasonRequired(Exception):
    pass


def check_overrides(
    violations: Sequence[Violation],
    *,
    org_settings: OrgSettings | None,
    acknowledged: Collection[str],
    reason: str | None,
) -> list[str]:
    """Return the overridden codes; raise OverrideRequired / OverrideReasonRequired."""
    seating = [v.code for v in violations if v.code in ALL_CODES]
    if seating:
        raise ValueError(f"seating override codes need #585: {', '.join(seating)}")

    acked = set(acknowledged)
    unacknowledged = [v for v in violations if v.code not in acked]
    codes = [v.code for v in violations]
    log.info(
        "override_checked",
        system="events",
        subsystem="overrides",
        codes=codes,
        unacknowledged=[v.code for v in unacknowledged],
    )
    if unacknowledged:
        raise OverrideRequired(unacknowledged)
    if codes and not (reason or "").strip():
        raise OverrideReasonRequired("An override needs a reason.")
    return codes
