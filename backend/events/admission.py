"""Whether members may add themselves to an event (self-serve signups)."""

from typing import Protocol

from django.db.models import Q

from app.models import CustomUser
from events.constants import EventState
from events.models import Event
from org.conduct.constants import CONDUCT_BLOCK_MESSAGE, Tier
from org.conduct.enforcement import tier_for
from org.conduct.gate import ConductGate, conduct_gate
from telemetry.logging import get_logger

log = get_logger(__name__)

NOT_ACCEPTING_MESSAGE = "Event is not accepting signups."
SELF_SERVE_DISABLED_MESSAGE = (
    "Self sign-ups are disabled for this event; ask an organizer to add you."
)


_PRE_START_STATES: frozenset[str] = frozenset(
    {EventState.UPCOMING, EventState.SIGNUPS_OPEN, EventState.ROLL_CALL}
)


class SupportsAdmission(Protocol):
    state: str
    allow_user_signups: bool


def self_serve_open_q() -> Q:
    return Q(state=EventState.SIGNUPS_OPEN, allow_user_signups=True)


def self_serve_offered(event: SupportsAdmission) -> bool:
    """Whether signup posts show Sign Up and Tentative."""
    return self_serve_refusal(event) is None


def decline_offered(event: SupportsAdmission) -> bool:
    """Whether signup posts show Decline: players may drop out until the start."""
    return event.state in _PRE_START_STATES


def self_serve_refusal(event: SupportsAdmission) -> str | None:
    if event.state != EventState.SIGNUPS_OPEN:
        return NOT_ACCEPTING_MESSAGE
    if not event.allow_user_signups:
        return SELF_SERVE_DISABLED_MESSAGE
    return None


def ensure_self_serve(
    event: Event, user: CustomUser, *, gate: ConductGate | None = None
) -> None:
    """Raise ValueError when ``user`` may not add themselves to ``event``."""
    reason = self_serve_refusal(event)
    if reason is None:
        _ensure_conduct_allows(event, user, gate)
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


def _ensure_conduct_allows(
    event: Event, user: CustomUser, gate: ConductGate | None
) -> None:
    if gate is None:
        gate = conduct_gate(event.organization_id)
    tier = tier_for(gate, user)
    if tier != Tier.BLOCK:
        return
    log.info(
        "conduct_signup_refused",
        system="org",
        subsystem="conduct",
        org_id=event.organization_id,
        event_id=event.pk,
        user_id=user.pk,
        tier=tier.value,
    )
    raise ValueError(CONDUCT_BLOCK_MESSAGE)
