from collections.abc import Mapping, Sequence

from django.db.models import Q

from events.constants import SignupStatus, VoicePresenceSource
from events.models import (
    Event,
    EventSignup,
    EventVoicePresence,
    ReadyCheck,
)
from events.ready_check_constants import (
    ReadyCheckEntryState,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from org.conduct.constants import Outcome, OutcomeSource
from org.models import OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)

Resolution = tuple[Outcome, OutcomeSource]

QUALIFYING_CHECK_OUTCOMES: tuple[str, ...] = (
    ReadyCheckOutcome.BINDING,
    ReadyCheckOutcome.STAFF_VERIFIED,
    ReadyCheckOutcome.STAFF_RESOLVED,
)


def qualifying_ready_check(event: Event) -> ReadyCheck | None:
    return (
        event.ready_checks.filter(
            phase=ReadyCheckPhase.CLOSED,
            outcome__in=QUALIFYING_CHECK_OUTCOMES,
            settings_snapshot__roll_call_enabled=True,
        )
        .order_by("-closed_at")
        .first()
    )


def _no_check_reason(event: Event) -> str:
    phases = set(event.ready_checks.values_list("phase", flat=True))
    phases.discard(ReadyCheckPhase.CANCELLED)
    if not phases:
        return "no_check"
    if ReadyCheckPhase.CLOSED in phases:
        return "non_binding"
    return "not_closed"


def _entry_states(event: Event) -> dict[int, str]:
    check = qualifying_ready_check(event)
    if check is None:
        log.debug(
            "conduct_auto_source_skipped",
            system="org",
            subsystem="conduct",
            org_id=event.organization_id,
            event_id=event.pk,
            reason=_no_check_reason(event),
        )
        return {}
    return dict(check.entries.values_list("user_id", "state"))


def _voice_user_ids(event: Event, user_ids: set[int]) -> set[int]:
    if not user_ids:
        return set()
    return set(
        EventVoicePresence.objects.filter(event_id=event.pk, user_id__in=user_ids)
        .filter(
            Q(present=True, source=VoicePresenceSource.FEED)
            | Q(first_joined_at__isnull=False)
        )
        .values_list("user_id", flat=True)
    )


def automatic_outcomes(
    event: Event,
    org_users: Mapping[int, OrgUser],
    signups: Sequence[EventSignup],
) -> dict[int, Resolution]:
    entries = _entry_states(event)
    voice = _voice_user_ids(
        event, {s.user_id for s in signups if s.status != SignupStatus.DROPPED}
    )

    result: dict[int, Resolution] = {}
    for signup in signups:
        org_user = org_users[signup.user_id]
        state = entries.get(signup.user_id)
        if signup.status == SignupStatus.DROPPED:
            if state == ReadyCheckEntryState.DROPPED:
                result[org_user.pk] = (Outcome.NO_SHOW, OutcomeSource.READY_CHECK)
            else:
                # The start cull (#533) will attribute these as OutcomeSource.CULL.
                log.debug(
                    "conduct_auto_source_skipped",
                    system="org",
                    subsystem="conduct",
                    org_id=event.organization_id,
                    event_id=event.pk,
                    org_user_id=org_user.pk,
                    reason="unattributed_drop",
                )
            continue
        if state == ReadyCheckEntryState.CONFIRMED:
            result[org_user.pk] = (Outcome.ATTENDED, OutcomeSource.READY_CHECK)
        elif signup.user_id in voice:
            result[org_user.pk] = (Outcome.ATTENDED, OutcomeSource.VOICE)
    return result
