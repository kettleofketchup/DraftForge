from dataclasses import dataclass
from enum import StrEnum

from django.db.models import Q

from app.models import CustomUser
from events.constants import EventState, SignupStatus
from events.models import Event
from tournament.models import Tournament


class RosterPhase(StrEnum):
    SIGNUPS = "signups"
    ROLL_CALL = "roll_call"
    START_FROM_SIGNUPS = "start_from_signups"


_CONFIRMED_ONLY: frozenset[SignupStatus] = frozenset({SignupStatus.CONFIRMED})
_APPROVED_AND_CONFIRMED: frozenset[SignupStatus] = frozenset(
    {SignupStatus.APPROVED, SignupStatus.CONFIRMED}
)
_DROPPED: frozenset[SignupStatus] = frozenset({SignupStatus.DROPPED})


@dataclass(frozen=True)
class RosterSyncResult:
    tournament: Tournament
    added: list[CustomUser]
    removed: list[CustomUser]
    kept_on_team: list[CustomUser]


def roster_phase(event: Event) -> RosterPhase:
    if event.state == EventState.ROLL_CALL:
        return RosterPhase.ROLL_CALL
    return RosterPhase.SIGNUPS


def start_phase(event: Event) -> RosterPhase:
    """Phase whose rule decides the roster when the tournament starts."""
    if event.state == EventState.ROLL_CALL:
        return RosterPhase.ROLL_CALL
    return RosterPhase.START_FROM_SIGNUPS


def roster_statuses(
    event: Event, phase: RosterPhase | None = None
) -> frozenset[SignupStatus]:
    """Signup statuses that belong on the event's tournament roster in a phase."""
    phase = phase or roster_phase(event)
    if phase == RosterPhase.ROLL_CALL:
        return _CONFIRMED_ONLY
    if phase == RosterPhase.START_FROM_SIGNUPS:
        return _APPROVED_AND_CONFIRMED
    return _CONFIRMED_ONLY if event.roll_call_enabled else _APPROVED_AND_CONFIRMED


def leaving_statuses(
    event: Event, phase: RosterPhase | None = None
) -> frozenset[SignupStatus]:
    """Statuses that do not belong on the roster in a phase; DROPPED never does."""
    return (_APPROVED_AND_CONFIRMED - roster_statuses(event, phase)) | _DROPPED


def joins_roster(event: Event, status: str, phase: RosterPhase | None = None) -> bool:
    return status in roster_statuses(event, phase)


def team_bound_user_pks(tournament: Tournament) -> set[int]:
    """Members, captains and deputies of any team in the tournament.

    Removing one of them from ``tournament.users`` cascades into the team
    (member removal, captain succession, empty-team deletion), so roster
    writes leave them in place.
    """
    return set(
        CustomUser.objects.nocache()
        .filter(
            Q(teams_as_member__tournament=tournament)
            | Q(teams_as_captain__tournament=tournament)
            | Q(teams_as_deputy_captain__tournament=tournament)
        )
        .values_list("pk", flat=True)
        .distinct()
    )
