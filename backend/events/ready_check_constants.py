from typing import Final

from django.db import models

from events.constants import SignupStatus

REMOVED_SIGNUP_STATUSES: Final[tuple[str, ...]] = (
    SignupStatus.CANCELLED,
    SignupStatus.REJECTED,
    SignupStatus.DROPPED,
)


class ReadyCheckScope(models.TextChoices):
    MAIN_ONLY = "main_only", "Main roster only"
    MAIN_AND_FILL = "main_and_fill", "Main roster and fill list"


class ReadyCheckLowCompletionAction(models.TextChoices):
    NON_BINDING = "non_binding", "Make the check non-binding (drop nobody)"
    HOLD_FOR_STAFF = (
        "hold_for_staff",
        "Hold drops for staff, the host or helpers to decide",
    )
    DROP_ANYWAY = "drop_anyway", "Drop unconfirmed anyway"


class PostCullFillMode(models.TextChoices):
    NONE = "none", "Do not fill"
    LINE_ORDER = "line_order", "Line order"
    VOICE_ARRIVAL = "voice_arrival", "Order of arrival in the event call"


class ReadyCheckPhase(models.TextChoices):
    OPEN = "open", "Open"
    ESCALATED = "escalated", "Escalated"
    HELD = "held", "Held for staff"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"


class ReadyCheckOutcome(models.TextChoices):
    BINDING = "binding", "Binding"
    NON_BINDING = "non_binding", "Non-binding"
    STAFF_VERIFIED = "staff_verified", "Staff-verified"
    STAFF_RESOLVED = "staff_resolved", "Resolved by staff"


class ReadyCheckEntryState(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    DROPPED = "dropped", "Dropped"
    EXCUSED = "excused", "Kept by staff"


class ReadyCheckConfirmVia(models.TextChoices):
    DISCORD = "discord", "Discord"
    WEB = "web", "Web"
    VOICE = "voice", "Voice channel"
    STAFF = "staff", "Staff"


DROPPED_SIGNUP_MESSAGE: Final = "You were dropped from this event"
READY_CHECK_MAX_MINUTES: Final = 1440
START_CULL_MAX_MINUTES: Final = 120
READY_CHECK_FIELD_RANGES: Final[dict[str, tuple[int, int]]] = {
    "ready_check_open_minutes": (1, READY_CHECK_MAX_MINUTES),
    "ready_check_escalation_minutes": (0, READY_CHECK_MAX_MINUTES),
    "ready_check_close_minutes": (0, READY_CHECK_MAX_MINUTES),
    "ready_check_chase_minutes": (1, READY_CHECK_MAX_MINUTES),
    "ready_check_min_completion_pct": (0, 100),
    "start_cull_minutes_after": (0, START_CULL_MAX_MINUTES),
}
