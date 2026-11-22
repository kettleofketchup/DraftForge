from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone as tz

from app.cache_utils import invalidate_after_commit
from events.capacity import lock_event
from events.constants import SignupAction, SignupStatus
from events.ledger import (
    SignupActor,
    record_ready_check_transition,
    record_signup_change,
    snapshot,
)
from events.models import Event, EventSignup, ReadyCheck, ReadyCheckEntry, RollCallMode
from events.ready_check_constants import (
    ReadyCheckEntryState,
    ReadyCheckPhase,
    ReadyCheckScope,
)
from telemetry.logging import get_logger

__all__ = [
    "ACCEPTING_PHASES",
    "LIVE_PHASES",
    "cancel_ready_check",
    "check_mode",
    "check_scope",
    "effective_mode",
    "end_ready_check_on_completion",
    "enrol_signup_if_live",
    "live_ready_check",
    "ready_check_population",
    "ready_check_promotion_status",
    "scope_statuses",
]

log = get_logger(__name__)

LIVE_PHASES: tuple[str, ...] = (
    ReadyCheckPhase.OPEN,
    ReadyCheckPhase.ESCALATED,
    ReadyCheckPhase.HELD,
    ReadyCheckPhase.CLOSED,
)
ACCEPTING_PHASES: tuple[str, ...] = (ReadyCheckPhase.OPEN, ReadyCheckPhase.ESCALATED)

_MAIN_STATUSES: tuple[str, ...] = (SignupStatus.APPROVED, SignupStatus.CONFIRMED)


def effective_mode(event: Event) -> str:
    if (
        event.roll_call_enabled
        and event.roll_call_mode == RollCallMode.AUTOMATIC
        and settings.READY_CHECK_AUTOMATIC_LIVE
    ):
        return RollCallMode.AUTOMATIC
    return RollCallMode.MANUAL


def check_mode(check: ReadyCheck, event: Event) -> str:
    return check.settings_snapshot.get("effective_mode") or effective_mode(event)


def check_scope(check: ReadyCheck, event: Event) -> str:
    return check.settings_snapshot.get("ready_check_scope") or event.ready_check_scope


def scope_statuses(scope: str) -> tuple[str, ...]:
    if scope == ReadyCheckScope.MAIN_AND_FILL:
        return (*_MAIN_STATUSES, SignupStatus.WAITLISTED)
    return _MAIN_STATUSES


def live_ready_check(event: Event, *, lock: bool = False) -> ReadyCheck | None:
    qs = ReadyCheck.objects.filter(event_id=event.pk, phase__in=LIVE_PHASES)
    if lock:
        qs = qs.select_for_update()
    return qs.first()


def ready_check_population(event: Event, scope: str) -> QuerySet[EventSignup]:
    return (
        EventSignup.objects.nocache()
        .filter(event_id=event.pk, status__in=scope_statuses(scope))
        .select_related("user")
    )


def _actor_user_id(actor: SignupActor) -> int | None:
    return actor.user.pk if actor.user is not None else None


@transaction.atomic
def cancel_ready_check(event: Event, *, actor: SignupActor, reason: str) -> bool:
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None:
        return False
    previous_phase = check.phase
    now = tz.now()
    updated = (
        ReadyCheck.objects.filter(pk=check.pk)
        .exclude(phase=ReadyCheckPhase.CANCELLED)
        .update(phase=ReadyCheckPhase.CANCELLED, cancelled_at=now, last_progress_at=now)
    )
    if not updated:
        return False
    check.refresh_from_db()
    correlation_id = f"rc{check.pk}:cancel"
    pending = list(
        check.entries.filter(state=ReadyCheckEntryState.PENDING).select_related(
            "user", "signup"
        )
    )
    for entry in pending:
        record_signup_change(
            event=locked,
            subject=entry.user,
            actor=actor,
            action=SignupAction.READY_CHECK_WITHDRAWN,
            signup=entry.signup,
            after=snapshot(entry.signup) if entry.signup is not None else None,
            reason=reason,
            correlation_id=correlation_id,
        )
    record_ready_check_transition(
        event=locked,
        actor=actor,
        check=check,
        step="cancel",
        reason=reason,
        extra={"previous_phase": previous_phase, "withdrawn": len(pending)},
    )
    fields: dict[str, Any] = {
        "event_id": locked.pk,
        "ready_check_id": check.pk,
        "phase": check.phase,
        "outcome": check.outcome,
        "previous_phase": previous_phase,
        "reason": reason,
        "withdrawn": len(pending),
        "actor_user_id": _actor_user_id(actor),
    }
    transaction.on_commit(
        lambda: log.info(
            "ready_check_cancelled",
            system="events",
            subsystem="ready_check",
            **fields,
        )
    )
    return True


def _confirm_signup_from_entry(
    signup: EventSignup, check: ReadyCheck, *, actor: SignupActor
) -> None:
    updated = (
        EventSignup.objects.nocache()
        .filter(pk=signup.pk, status=SignupStatus.APPROVED)
        .update(status=SignupStatus.CONFIRMED)
    )
    if not updated:
        return
    before = snapshot(signup)
    signup.status = SignupStatus.CONFIRMED
    event = signup.event
    tournament = event.tournament
    invalidate_after_commit(signup)
    if tournament is not None and tournament.state == "future":
        tournament.users.add(signup.user)
        invalidate_after_commit(tournament)
    record_signup_change(
        event=event,
        subject=signup.user,
        actor=actor,
        action=SignupAction.CONFIRMED,
        signup=signup,
        before=before,
        after=snapshot(signup),
        reason="ready_check_entry_confirmed",
        correlation_id=f"rc{check.pk}:enrol",
    )


def enrol_signup_if_live(
    signup: EventSignup, *, actor: SignupActor
) -> ReadyCheckEntry | None:
    event = signup.event
    check = live_ready_check(event, lock=True)
    if check is None:
        return None
    entry = check.entries.filter(user_id=signup.user_id).first()
    if entry is not None:
        if (
            entry.state == ReadyCheckEntryState.CONFIRMED
            and signup.status == SignupStatus.APPROVED
        ):
            _confirm_signup_from_entry(signup, check, actor=actor)
        return entry
    if check.phase not in ACCEPTING_PHASES:
        return None
    if signup.status not in scope_statuses(check_scope(check, event)):
        return None
    entry = ReadyCheckEntry.for_signup(check, signup)
    entry.save()
    record_signup_change(
        event=event,
        subject=signup.user,
        actor=actor,
        action=SignupAction.READY_CHECK_ASKED,
        signup=signup,
        after=snapshot(signup),
        reason="ready_check_late_enrolment",
        correlation_id=f"rc{check.pk}:enrol",
    )
    fields: dict[str, Any] = {
        "event_id": event.pk,
        "ready_check_id": check.pk,
        "phase": check.phase,
        "signup_id": signup.pk,
        "actor_user_id": _actor_user_id(actor),
    }
    transaction.on_commit(
        lambda: log.info(
            "ready_check_member_enrolled",
            system="events",
            subsystem="ready_check",
            **fields,
        )
    )
    return entry


def ready_check_promotion_status(
    event: Event, decided: str, signup: EventSignup
) -> str:
    check = live_ready_check(event)
    if check is None:
        return decided
    if check.entries.filter(
        user_id=signup.user_id, state=ReadyCheckEntryState.CONFIRMED
    ).exists():
        return SignupStatus.CONFIRMED
    if (
        decided == SignupStatus.CONFIRMED
        and check_mode(check, event) == RollCallMode.AUTOMATIC
    ):
        return SignupStatus.APPROVED
    return decided


@transaction.atomic
def end_ready_check_on_completion(event: Event, *, actor: SignupActor) -> bool:
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None or check.phase == ReadyCheckPhase.CLOSED:
        return False
    return cancel_ready_check(locked, actor=actor, reason="event_completed")
