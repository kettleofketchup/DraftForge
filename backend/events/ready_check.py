from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.db import transaction
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
    ReadyCheckPhase,
)
from events.ready_check_core import (
    ACCEPTING_PHASES,
    cancel_ready_check,
    check_scope,
    effective_mode,
    live_ready_check,
    ready_check_population,
    scope_statuses,
)
from events.ready_check_settings import ready_check_settings_snapshot
from events.ready_check_signals import (
    ReadyCheckChange,
    ready_check_member_confirmed,
    ready_check_opened,
    send_on_commit,
)
from events.roster import RosterSyncResult
from events.services import add_user_to_tournament, sync_event_roster
from telemetry.logging import get_logger

__all__ = [
    "ConfirmResult",
    "OpenResult",
    "cancel_ready_check",
    "confirm_ready",
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
