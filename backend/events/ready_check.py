from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.db import transaction
from django.dispatch import Signal
from django.utils import timezone as tz

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Team
from events.capacity import lock_event
from events.constants import EventState, SignupAction, SignupStatus
from events.ledger import (
    SignupActor,
    record_ready_check_transition,
    record_signup_change,
    snapshot,
)
from events.models import Event, EventSignup, ReadyCheck, ReadyCheckEntry, RollCallMode
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckLowCompletionAction,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from events.ready_check_core import (
    ACCEPTING_PHASES,
    cancel_ready_check,
    check_mode,
    check_scope,
    effective_mode,
    live_ready_check,
    ready_check_population,
    scope_statuses,
)
from events.ready_check_settings import ready_check_settings_snapshot
from events.ready_check_signals import (
    ReadyCheckChange,
    ready_check_chase_due,
    ready_check_closed,
    ready_check_escalated,
    ready_check_held,
    ready_check_member_confirmed,
    ready_check_member_dropped,
    ready_check_opened,
    ready_check_went_non_binding,
    send_on_commit,
)
from events.roster import RosterSyncResult
from events.services import (
    _promote_from_waitlist,
    _roster_remove_if_left,
    add_user_to_tournament,
    sync_event_roster,
)
from telemetry.logging import get_logger

__all__ = [
    "CloseResult",
    "ConfirmResult",
    "OpenResult",
    "cancel_ready_check",
    "chase_unconfirmed",
    "close_ready_check",
    "confirm_ready",
    "escalate_ready_check",
    "live_ready_check",
    "lock_event",
    "open_ready_check",
    "refused_confirm_message",
]

log = get_logger(__name__)

IN_PROGRESS_MESSAGE = "The tournament is already running."
TEAMS_MADE_MESSAGE = "Teams are already made for this event."


class ConfirmResult(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_CONFIRMED = "already_confirmed"
    CLOSED = "closed"
    NOT_IN_CHECK = "not_in_check"


@dataclass(frozen=True)
class OpenResult:
    check: ReadyCheck
    created: bool
    roster: RosterSyncResult | None


@dataclass(frozen=True)
class CloseResult:
    check: ReadyCheck | None
    changed: bool
    dropped_user_ids: tuple[int, ...] = ()
    promoted_signup_ids: tuple[int, ...] = ()


_DROPPABLE_STATUSES: tuple[str, ...] = (SignupStatus.APPROVED, SignupStatus.WAITLISTED)


def _actor_user_id(actor: SignupActor) -> int | None:
    return actor.user.pk if actor.user is not None else None


def _teams_made(event: Event) -> bool:
    tournament = event.tournament
    if tournament is None:
        return False
    return (
        tournament.state != "future"
        or Team.objects.filter(tournament=tournament).exists()
    )


def _refuse_open(event: Event) -> None:
    if event.state == EventState.IN_PROGRESS:
        raise ValueError(IN_PROGRESS_MESSAGE)
    if event.state not in (EventState.SIGNUPS_OPEN, EventState.ROLL_CALL):
        raise ValueError(f"Cannot open a ready check from '{event.state}' state.")
    if _teams_made(event):
        raise ValueError(TEAMS_MADE_MESSAGE)


def _snapshot_settings(event: Event) -> dict[str, Any]:
    return ready_check_settings_snapshot(event) | {
        "roll_call_enabled": event.roll_call_enabled,
        "effective_mode": effective_mode(event),
        "configured_mode": event.roll_call_mode,
    }


def _reset_confirmed(
    locked: Event, signup: EventSignup, *, actor: SignupActor, correlation_id: str
) -> None:
    updated = (
        EventSignup.objects.nocache()
        .filter(pk=signup.pk, status=SignupStatus.CONFIRMED)
        .update(status=SignupStatus.APPROVED, updated_at=tz.now())
    )
    if not updated:
        return
    before = snapshot(signup)
    signup.status = SignupStatus.APPROVED
    record_signup_change(
        event=locked,
        subject=signup.user,
        actor=actor,
        action=SignupAction.UNCONFIRMED,
        signup=signup,
        before=before,
        after=snapshot(signup),
        reason="ready_check_reset",
        correlation_id=correlation_id,
    )


@transaction.atomic
def open_ready_check(event: Event, *, actor: SignupActor) -> OpenResult:
    locked = lock_event(event)
    existing = live_ready_check(locked, lock=True)
    if existing is not None:
        if locked.state == EventState.ROLL_CALL:
            return OpenResult(
                check=existing, created=False, roster=sync_event_roster(locked)
            )
        stale_fields: dict[str, Any] = {
            "event_id": locked.pk,
            "ready_check_id": existing.pk,
            "phase": existing.phase,
            "event_state": locked.state,
            "actor_user_id": _actor_user_id(actor),
        }
        cancel_ready_check(locked, actor=actor, reason="stale_check")
        transaction.on_commit(
            lambda: log.warning(
                "ready_check_stale_cancelled",
                system="events",
                subsystem="ready_check",
                **stale_fields,
            )
        )

    _refuse_open(locked)
    transitioned = locked.state == EventState.SIGNUPS_OPEN
    if transitioned:
        locked.transition_state(EventState.ROLL_CALL)
        event.state = locked.state

    settings_snapshot = _snapshot_settings(locked)
    mode = settings_snapshot["effective_mode"]
    now = tz.now()
    check = ReadyCheck.objects.create(
        event=locked,
        settings_snapshot=settings_snapshot,
        opened_at=now,
        last_progress_at=now,
        opened_by=actor.user,
    )
    correlation_id = f"rc{check.pk}:open"

    signups = list(ready_check_population(locked, check_scope(check)))
    entries: list[ReadyCheckEntry] = []
    for signup in signups:
        entry = ReadyCheckEntry.for_signup(check, signup)
        if signup.status == SignupStatus.CONFIRMED:
            if mode == RollCallMode.AUTOMATIC:
                _reset_confirmed(
                    locked, signup, actor=actor, correlation_id=correlation_id
                )
            else:
                entry.state = ReadyCheckEntryState.CONFIRMED
                entry.confirmed_via = ReadyCheckConfirmVia.STAFF
                entry.confirmed_at = now
        entries.append(entry)
    ReadyCheckEntry.objects.bulk_create(entries)

    for signup in signups:
        record_signup_change(
            event=locked,
            subject=signup.user,
            actor=actor,
            action=SignupAction.READY_CHECK_ASKED,
            signup=signup,
            after=snapshot(signup),
            reason="ready_check_opened",
            correlation_id=correlation_id,
        )

    roster = sync_event_roster(locked)
    invalidate_after_commit(locked, *signups)

    pending_user_ids = tuple(
        entry.user_id
        for entry in entries
        if entry.state == ReadyCheckEntryState.PENDING
    )
    confirmed_count = len(entries) - len(pending_user_ids)
    record_ready_check_transition(
        event=locked,
        actor=actor,
        check=check,
        step="open",
        extra={
            "mode": mode,
            "asked": len(entries),
            "pending": len(pending_user_ids),
            "confirmed": confirmed_count,
            "transitioned": transitioned,
        },
    )
    if not transitioned:
        locked.refresh_signup_post_on_commit()
    send_on_commit(
        ready_check_opened,
        ReadyCheckChange(
            event_id=locked.pk,
            ready_check_id=check.pk,
            phase=check.phase,
            outcome=check.outcome,
            user_ids=pending_user_ids,
            actor_user_id=_actor_user_id(actor),
        ),
    )
    fields: dict[str, Any] = {
        "event_id": locked.pk,
        "ready_check_id": check.pk,
        "phase": check.phase,
        "mode": mode,
        "asked": len(entries),
        "pending": len(pending_user_ids),
        "confirmed": confirmed_count,
        "transitioned": transitioned,
        "actor_user_id": _actor_user_id(actor),
    }
    transaction.on_commit(
        lambda: log.info(
            "ready_check_opened",
            system="events",
            subsystem="ready_check",
            **fields,
        )
    )
    return OpenResult(check=check, created=True, roster=roster)


def _log_refused(
    event: Event, check: ReadyCheck | None, user: CustomUser, result: ConfirmResult
) -> ConfirmResult:
    log.debug(
        "ready_check_confirm_refused",
        system="events",
        subsystem="ready_check",
        event_id=event.pk,
        ready_check_id=check.pk if check is not None else None,
        phase=check.phase if check is not None else None,
        outcome=str(result),
        user_id=user.pk,
    )
    return result


def _confirm_entry(entry: ReadyCheckEntry, via: str) -> bool:
    now = tz.now()
    updated = ReadyCheckEntry.objects.filter(
        pk=entry.pk, state=ReadyCheckEntryState.PENDING
    ).update(state=ReadyCheckEntryState.CONFIRMED, confirmed_via=via, confirmed_at=now)
    entry.refresh_from_db()
    return bool(updated)


def _sync_signup_confirmed(locked: Event, signup: EventSignup) -> bool:
    if signup.status != SignupStatus.APPROVED:
        return False
    updated = (
        EventSignup.objects.nocache()
        .filter(pk=signup.pk, status=SignupStatus.APPROVED)
        .update(status=SignupStatus.CONFIRMED, updated_at=tz.now())
    )
    if not updated:
        return False
    signup.status = SignupStatus.CONFIRMED
    add_user_to_tournament(locked, signup.user)
    return True


@transaction.atomic
def confirm_ready(
    event: Event,
    user: CustomUser,
    *,
    via: ReadyCheckConfirmVia | str,
    actor: SignupActor,
) -> ConfirmResult:
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if locked.state != EventState.ROLL_CALL:
        return _log_refused(locked, check, user, ConfirmResult.CLOSED)
    if check is None:
        return _log_refused(locked, check, user, ConfirmResult.NOT_IN_CHECK)
    entry = check.entries.filter(user_id=user.pk).first()
    if entry is None or entry.signup_id is None:
        return _log_refused(locked, check, user, ConfirmResult.NOT_IN_CHECK)
    if entry.state in (ReadyCheckEntryState.DROPPED, ReadyCheckEntryState.EXCUSED):
        return _log_refused(locked, check, user, ConfirmResult.CLOSED)
    signup = (
        EventSignup.objects.nocache().select_related("user").get(pk=entry.signup_id)
    )
    if signup.status not in scope_statuses(check_scope(check)):
        return _log_refused(locked, check, user, ConfirmResult.NOT_IN_CHECK)

    before = snapshot(signup)
    entry_changed = False
    if entry.state == ReadyCheckEntryState.PENDING:
        staff_on_held = (
            via == ReadyCheckConfirmVia.STAFF and check.phase == ReadyCheckPhase.HELD
        )
        if check.phase not in ACCEPTING_PHASES and not staff_on_held:
            return _log_refused(locked, check, user, ConfirmResult.CLOSED)
        entry_changed = _confirm_entry(entry, via)
        if not entry_changed and entry.state != ReadyCheckEntryState.CONFIRMED:
            return _log_refused(locked, check, user, ConfirmResult.CLOSED)

    signup_changed = _sync_signup_confirmed(locked, signup)
    result = (
        ConfirmResult.CONFIRMED if entry_changed else ConfirmResult.ALREADY_CONFIRMED
    )
    if not (entry_changed or signup_changed):
        return result

    now = tz.now()
    ReadyCheck.objects.filter(pk=check.pk).update(last_progress_at=now)
    check.last_progress_at = now
    record_signup_change(
        event=locked,
        subject=signup.user,
        actor=actor,
        action=SignupAction.CONFIRMED,
        signup=signup,
        before=before,
        after=snapshot(signup),
        reason="ready_check_confirmed",
        correlation_id=f"rc{check.pk}:confirm",
    )
    invalidate_after_commit(signup, locked)
    locked.refresh_signup_post_on_commit()
    send_on_commit(
        ready_check_member_confirmed,
        ReadyCheckChange(
            event_id=locked.pk,
            ready_check_id=check.pk,
            phase=check.phase,
            outcome=check.outcome,
            user_ids=(user.pk,),
            actor_user_id=_actor_user_id(actor),
        ),
    )
    fields: dict[str, Any] = {
        "event_id": locked.pk,
        "ready_check_id": check.pk,
        "phase": check.phase,
        "outcome": str(result),
        "via": str(via),
        "signup_id": signup.pk,
        "entry_changed": entry_changed,
        "signup_changed": signup_changed,
        "actor_user_id": _actor_user_id(actor),
    }
    transaction.on_commit(
        lambda: log.info(
            "ready_check_member_confirmed",
            system="events",
            subsystem="ready_check",
            **fields,
        )
    )
    return result


def refused_confirm_message(event: Event, *, held: bool = False) -> str:
    status = "is waiting on staff" if held else "has closed"
    host = event.host
    if host is None:
        contact = "Contact the event staff"
    else:
        contact = f"Contact the host, {host.nickname or host.username},"
    return f"The ready check for {event.name} {status}. {contact} to be added back."


def _change(
    check: ReadyCheck, user_ids: Sequence[int], actor: SignupActor
) -> ReadyCheckChange:
    return ReadyCheckChange(
        event_id=check.event_id,
        ready_check_id=check.pk,
        phase=check.phase,
        outcome=check.outcome,
        user_ids=tuple(user_ids),
        actor_user_id=_actor_user_id(actor),
    )


def _active_and_droppable(
    check: ReadyCheck,
) -> tuple[list[ReadyCheckEntry], list[ReadyCheckEntry]]:
    statuses = scope_statuses(check_scope(check))
    active = [
        entry
        for entry in check.entries.select_related("signup", "user").order_by("pk")
        if entry.signup is not None and entry.signup.status in statuses
    ]
    droppable = [
        entry
        for entry in active
        if entry.state == ReadyCheckEntryState.PENDING
        and entry.signup is not None
        and entry.signup.status in _DROPPABLE_STATUSES
    ]
    return active, droppable


def _pending(entries: Sequence[ReadyCheckEntry]) -> list[ReadyCheckEntry]:
    return [entry for entry in entries if entry.state == ReadyCheckEntryState.PENDING]


def _record_member_rows(
    locked: Event,
    entries: Sequence[ReadyCheckEntry],
    *,
    actor: SignupActor,
    action: SignupAction,
    reason: str,
    correlation_id: str,
) -> None:
    for entry in entries:
        record_signup_change(
            event=locked,
            subject=entry.user,
            actor=actor,
            action=action,
            signup=entry.signup,
            after=snapshot(entry.signup) if entry.signup is not None else None,
            reason=reason,
            correlation_id=correlation_id,
        )


def _log_on_commit(event_name: str, fields: dict[str, Any]) -> None:
    transaction.on_commit(
        lambda: log.info(
            event_name,
            system="events",
            subsystem="ready_check",
            **fields,
        )
    )


def _nudge(
    locked: Event,
    check: ReadyCheck,
    *,
    actor: SignupActor,
    step: str,
    reason: str,
    signal: Signal,
    log_event: str,
) -> list[ReadyCheckEntry]:
    active, _ = _active_and_droppable(check)
    pending = _pending(active)
    _record_member_rows(
        locked,
        pending,
        actor=actor,
        action=SignupAction.READY_CHECK_NUDGED,
        reason=reason,
        correlation_id=f"rc{check.pk}:{step}",
    )
    record_ready_check_transition(
        event=locked,
        actor=actor,
        check=check,
        step=step,
        extra={"pending": len(pending), "active": len(active)},
    )
    user_ids = [entry.user_id for entry in pending]
    send_on_commit(signal, _change(check, user_ids, actor))
    _log_on_commit(
        log_event,
        {
            "event_id": locked.pk,
            "ready_check_id": check.pk,
            "phase": check.phase,
            "mode": check_mode(check),
            "pending": len(pending),
            "active": len(active),
            "actor_user_id": _actor_user_id(actor),
        },
    )
    return pending


@transaction.atomic
def escalate_ready_check(event: Event, *, actor: SignupActor) -> list[ReadyCheckEntry]:
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None or locked.state != EventState.ROLL_CALL:
        return []
    now = tz.now()
    updated = ReadyCheck.objects.filter(pk=check.pk, phase=ReadyCheckPhase.OPEN).update(
        phase=ReadyCheckPhase.ESCALATED, escalated_at=now, last_progress_at=now
    )
    if not updated:
        return []
    check.refresh_from_db()
    return _nudge(
        locked,
        check,
        actor=actor,
        step="escalate",
        reason="escalated",
        signal=ready_check_escalated,
        log_event="ready_check_escalated",
    )


@transaction.atomic
def chase_unconfirmed(event: Event, *, actor: SignupActor) -> list[ReadyCheckEntry]:
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None or locked.state != EventState.ROLL_CALL:
        return []
    updated = ReadyCheck.objects.filter(
        pk=check.pk, phase__in=ACCEPTING_PHASES, chased_at__isnull=True
    ).update(chased_at=tz.now())
    if not updated:
        return []
    check.refresh_from_db()
    return _nudge(
        locked,
        check,
        actor=actor,
        step="chase",
        reason="chase",
        signal=ready_check_chase_due,
        log_event="ready_check_chased",
    )


def _drop(
    locked: Event,
    check: ReadyCheck,
    entries: Sequence[ReadyCheckEntry],
    *,
    actor: SignupActor,
    step: str,
    reason: str = "ready_check_unconfirmed",
) -> tuple[list[int], list[int]]:
    correlation_id = f"rc{check.pk}:{step}"
    now = tz.now()
    dropped_user_ids: list[int] = []
    dropped_signups: list[EventSignup] = []
    for entry in entries:
        signup = entry.signup
        if signup is None:
            continue
        updated = (
            EventSignup.objects.nocache()
            .filter(pk=signup.pk, status__in=_DROPPABLE_STATUSES)
            .update(status=SignupStatus.DROPPED, waitlist_position=None, updated_at=now)
        )
        if not updated:
            continue
        before = snapshot(signup)
        signup.status = SignupStatus.DROPPED
        signup.waitlist_position = None
        signup.event = locked
        ReadyCheckEntry.objects.filter(pk=entry.pk).update(
            state=ReadyCheckEntryState.DROPPED, dropped_at=now
        )
        entry.state = ReadyCheckEntryState.DROPPED
        entry.dropped_at = now
        _roster_remove_if_left(signup)
        record_signup_change(
            event=locked,
            subject=entry.user,
            actor=actor,
            action=SignupAction.DROPPED,
            signup=signup,
            before=before,
            after=snapshot(signup),
            reason=reason,
            correlation_id=correlation_id,
        )
        dropped_user_ids.append(entry.user_id)
        dropped_signups.append(signup)
    promoted_signup_ids: list[int] = []
    if dropped_signups and locked.max_players:
        promoted_signup_ids = [
            promoted.pk
            for promoted in _promote_from_waitlist(
                locked, actor=actor, correlation_id=correlation_id
            )
        ]
    if dropped_signups:
        invalidate_after_commit(locked, *dropped_signups)
    return dropped_user_ids, promoted_signup_ids


@transaction.atomic
def close_ready_check(event: Event, *, actor: SignupActor) -> CloseResult:
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None:
        return CloseResult(check=None, changed=False)
    if locked.state != EventState.ROLL_CALL or check.phase not in ACCEPTING_PHASES:
        return CloseResult(check=check, changed=False)

    snap = check.settings_snapshot
    mode = check_mode(check)
    min_pct = int(snap["ready_check_min_completion_pct"])
    low_action = snap["ready_check_low_completion_action"]
    active, droppable = _active_and_droppable(check)
    pending = _pending(active)
    confirmed = sum(
        1 for entry in active if entry.state == ReadyCheckEntryState.CONFIRMED
    )
    completion_pct = confirmed * 100 // len(active) if active else 100
    threshold_met = confirmed * 100 >= min_pct * len(active)

    step = "close"
    dropped_user_ids: list[int] = []
    promoted_signup_ids: list[int] = []
    if mode != RollCallMode.AUTOMATIC:
        phase, outcome = ReadyCheckPhase.CLOSED, ReadyCheckOutcome.STAFF_VERIFIED
        member_rows = (SignupAction.READY_CHECK_KEPT, "staff_verified", pending)
    elif threshold_met or low_action == ReadyCheckLowCompletionAction.DROP_ANYWAY:
        phase, outcome = ReadyCheckPhase.CLOSED, ReadyCheckOutcome.BINDING
        member_rows = None
        dropped_user_ids, promoted_signup_ids = _drop(
            locked, check, droppable, actor=actor, step=step
        )
    elif low_action == ReadyCheckLowCompletionAction.HOLD_FOR_STAFF:
        step = "hold"
        phase, outcome = ReadyCheckPhase.HELD, ""
        member_rows = (SignupAction.READY_CHECK_HELD, "held_for_staff", droppable)
    else:
        phase, outcome = ReadyCheckPhase.CLOSED, ReadyCheckOutcome.NON_BINDING
        member_rows = (SignupAction.READY_CHECK_KEPT, "non_binding", pending)

    if member_rows is not None:
        action, reason, entries = member_rows
        _record_member_rows(
            locked,
            entries,
            actor=actor,
            action=action,
            reason=reason,
            correlation_id=f"rc{check.pk}:{step}",
        )

    now = tz.now()
    update_fields: dict[str, Any] = {
        "phase": phase,
        "outcome": outcome,
        "completion_pct": completion_pct,
        "last_progress_at": now,
    }
    if phase == ReadyCheckPhase.CLOSED:
        update_fields["closed_at"] = now
    ReadyCheck.objects.filter(pk=check.pk).update(**update_fields)
    check.refresh_from_db()

    counts: dict[str, Any] = {
        "mode": mode,
        "completion_pct": completion_pct,
        "min_completion_pct": min_pct,
        "active": len(active),
        "confirmed": confirmed,
        "pending": len(pending),
        "dropped": len(dropped_user_ids),
        "promoted": len(promoted_signup_ids),
    }
    record_ready_check_transition(
        event=locked, actor=actor, check=check, step=step, extra=counts
    )
    if dropped_user_ids or promoted_signup_ids:
        invalidate_after_commit(locked)
        locked.refresh_signup_post_on_commit()

    if phase == ReadyCheckPhase.HELD:
        send_on_commit(
            ready_check_held,
            _change(check, [entry.user_id for entry in droppable], actor),
        )
    else:
        pending_user_ids = [entry.user_id for entry in pending]
        if outcome == ReadyCheckOutcome.NON_BINDING:
            send_on_commit(
                ready_check_went_non_binding, _change(check, pending_user_ids, actor)
            )
        send_on_commit(ready_check_closed, _change(check, pending_user_ids, actor))
        if dropped_user_ids:
            send_on_commit(
                ready_check_member_dropped, _change(check, dropped_user_ids, actor)
            )
    _log_on_commit(
        "ready_check_held" if phase == ReadyCheckPhase.HELD else "ready_check_closed",
        {
            "event_id": locked.pk,
            "ready_check_id": check.pk,
            "phase": check.phase,
            "outcome": check.outcome,
            "low_completion_action": low_action,
            "actor_user_id": _actor_user_id(actor),
            **counts,
        },
    )
    return CloseResult(
        check=check,
        changed=True,
        dropped_user_ids=tuple(dropped_user_ids),
        promoted_signup_ids=tuple(promoted_signup_ids),
    )
