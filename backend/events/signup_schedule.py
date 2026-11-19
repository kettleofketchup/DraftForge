"""When an event's signups open, derived from its signup open policy."""

from datetime import datetime, timedelta

from events.constants import SignupOpenMode
from events.models import Event, EventConfigMixin

MAX_SIGNUPS_OPEN_HOURS_BEFORE = 24 * 60
SIGNUP_OPEN_POLICY_FIELDS: tuple[str, ...] = (
    "signup_open_mode",
    "signups_open_hours_before",
)


def compute_signups_open_at(
    config: EventConfigMixin, scheduled_at: datetime, now: datetime
) -> datetime | None:
    """None for manual; a past time is fine, the next open tick picks it up."""
    if config.signup_open_mode == SignupOpenMode.IMMEDIATE:
        return now
    if config.signup_open_mode == SignupOpenMode.SCHEDULED:
        return scheduled_at - timedelta(hours=config.signups_open_hours_before)
    return None


def apply_signup_open_policy(event: Event, now: datetime) -> None:
    event.signups_open_at = compute_signups_open_at(event, event.scheduled_at, now)


def policy_from_explicit_open_at(
    scheduled_at: datetime, signups_open_at: datetime | None
) -> dict[str, object]:
    """Policy fields matching a client-computed open time (pre-policy clients)."""
    if signups_open_at is None:
        return {"signup_open_mode": SignupOpenMode.MANUAL}
    hours = round((scheduled_at - signups_open_at) / timedelta(hours=1))
    return {
        "signup_open_mode": SignupOpenMode.SCHEDULED,
        "signups_open_hours_before": min(max(hours, 0), MAX_SIGNUPS_OPEN_HOURS_BEFORE),
    }
