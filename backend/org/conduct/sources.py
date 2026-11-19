from collections.abc import Mapping, Sequence

from events.models import Event, EventSignup, ReadyCheck
from events.ready_check_constants import ReadyCheckOutcome, ReadyCheckPhase
from org.conduct.constants import Outcome, OutcomeSource
from org.models import OrgUser

QUALIFYING_CHECK_OUTCOMES: tuple[str, ...] = (
    ReadyCheckOutcome.BINDING,
    ReadyCheckOutcome.STAFF_VERIFIED,
    ReadyCheckOutcome.STAFF_RESOLVED,
)


def qualifying_ready_check(event: Event) -> ReadyCheck | None:
    return (
        event.ready_checks.filter(
            phase=ReadyCheckPhase.CLOSED, outcome__in=QUALIFYING_CHECK_OUTCOMES
        )
        .order_by("-closed_at")
        .first()
    )


def automatic_outcomes(
    event: Event,
    org_users: Mapping[int, OrgUser],
    signups: Sequence[EventSignup],
) -> dict[int, tuple[Outcome, OutcomeSource]]:
    return {}
