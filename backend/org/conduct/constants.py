from decimal import Decimal
from enum import StrEnum
from typing import Final, Protocol

from django.db import models

from events.constants import REGISTERED_SIGNUP_STATUSES, EventState, SignupStatus


class Outcome(models.TextChoices):
    PENDING = "pending", "Pending"
    ATTENDED = "attended", "Attended"
    NO_SHOW = "no_show", "No-show"
    LATE_CANCEL = "late_cancel", "Late cancel"
    EXCUSED = "excused", "Excused"


STAFF_SETTABLE: Final[tuple[Outcome, ...]] = (
    Outcome.ATTENDED,
    Outcome.NO_SHOW,
    Outcome.LATE_CANCEL,
    Outcome.EXCUSED,
)
COUNTED: Final[tuple[Outcome, ...]] = (
    Outcome.ATTENDED,
    Outcome.NO_SHOW,
    Outcome.LATE_CANCEL,
)


class OutcomeSource(models.TextChoices):
    DEFAULT = "default", "Default"
    STAFF = "staff", "Staff"
    READY_CHECK = "ready_check", "Ready check"
    CULL = "cull", "Cull"
    VOICE = "voice", "Voice"
    LATE_CANCEL = "late_cancel", "Late cancel"


AUTOMATIC_SOURCES: Final[tuple[OutcomeSource, ...]] = (
    OutcomeSource.DEFAULT,
    OutcomeSource.READY_CHECK,
    OutcomeSource.CULL,
    OutcomeSource.VOICE,
)


class Tier(StrEnum):
    OK = "ok"
    BACK_OF_LINE = "back_of_line"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


TIER_SEVERITY: Final[dict[Tier, int]] = {
    Tier.OK: 0,
    Tier.BACK_OF_LINE: 1,
    Tier.REQUIRE_APPROVAL: 2,
    Tier.BLOCK: 3,
}

PRE_CLOSE_STATES: Final[frozenset[str]] = frozenset(
    {
        EventState.UPCOMING,
        EventState.SIGNUPS_OPEN,
        EventState.ROLL_CALL,
        EventState.IN_PROGRESS,
    }
)
EDITABLE_STATES: Final[frozenset[str]] = frozenset(
    {EventState.ROLL_CALL, EventState.IN_PROGRESS}
)

DEFAULT_LATE_CANCEL_HOURS: Final[int] = 2
DEFAULT_LATE_CANCEL_WEIGHT: Final[Decimal] = Decimal("0.50")
DEFAULT_HALF_LIFE_DAYS: Final[int] = 90
DEFAULT_MAX_AGE_DAYS: Final[int] = 365
DEFAULT_PRIOR_SHOW_RATE: Final[Decimal] = Decimal("0.85")
DEFAULT_PRIOR_STRENGTH: Final[Decimal] = Decimal("3.00")
DEFAULT_MIN_EVENTS: Final[int] = 3
DEFAULT_BACK_OF_LINE_BELOW: Final[Decimal] = Decimal("0.75")
DEFAULT_REQUIRE_APPROVAL_BELOW: Final[Decimal] = Decimal("0.65")
DEFAULT_BLOCK_BELOW: Final[Decimal] = Decimal("0.40")

SETTINGS_RANGES: Final[dict[str, tuple[Decimal | int, Decimal | int]]] = {
    "late_cancel_hours": (0, 168),
    "late_cancel_weight": (Decimal("0"), Decimal("1")),
    "half_life_days": (7, 730),
    "max_age_days": (30, 1095),
    "prior_show_rate": (Decimal("0.05"), Decimal("1")),
    "prior_strength": (Decimal("0"), Decimal("20")),
    "min_events": (1, 20),
    "back_of_line_below": (Decimal("0"), Decimal("1")),
    "require_approval_below": (Decimal("0"), Decimal("1")),
    "block_below": (Decimal("0"), Decimal("1")),
}

REASON_MIN_LENGTH: Final[int] = 3
REASON_MAX_LENGTH: Final[int] = 500

CONDUCT_BLOCK_MESSAGE: Final[str] = (
    "Your attendance record in this organization is below what it requires "
    "for self sign-up. Ask an organizer to add you."
)

FLAG_ROLL_CALL_UNCONFIRMED: Final[str] = "roll_call_unconfirmed"
FLAG_DROPPED_UNATTRIBUTED: Final[str] = "dropped_unattributed"


class SupportsApprovalMode(Protocol):
    auto_approve: bool


def expected_statuses(event: SupportsApprovalMode) -> frozenset[str]:
    statuses = set(REGISTERED_SIGNUP_STATUSES)
    if not event.auto_approve:
        statuses.add(SignupStatus.RSVP)
    return frozenset(statuses)
