"""Whether members may add themselves to an event (self-serve signups)."""

from typing import Protocol

from django.db.models import Q

from app.models import CustomUser
from events.constants import EventState
from events.models import Event
from telemetry.logging import get_logger

log = get_logger(__name__)

NOT_ACCEPTING_MESSAGE = "Event is not accepting signups."
SELF_SERVE_DISABLED_MESSAGE = (
    "Self sign-ups are disabled for this event; ask an organizer to add you."
)


class SupportsAdmission(Protocol):
    state: str
    allow_user_signups: bool


def self_serve_open_q() -> Q:
    return Q(state=EventState.SIGNUPS_OPEN, allow_user_signups=True)


def self_serve_offered(event: SupportsAdmission) -> bool:
    """Whether signup posts show the self-serve actions; state is checked on click."""
    return event.allow_user_signups


def self_serve_refusal(event: SupportsAdmission) -> str | None:
    if event.state != EventState.SIGNUPS_OPEN:
        return NOT_ACCEPTING_MESSAGE
    if not event.allow_user_signups:
        return SELF_SERVE_DISABLED_MESSAGE
    return None


def ensure_self_serve(event: Event, user: CustomUser) -> None:
    """Raise ValueError when ``user`` may not add themselves to ``event``."""
    reason = self_serve_refusal(event)
    if reason is None:
        return
    log.info(
        "signup_self_serve_refused",
        system="events",
        subsystem="services",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=event.pk,
        user_id=user.pk,
        reason=reason,
    )
    raise ValueError(reason)
