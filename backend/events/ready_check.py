from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from django.db import transaction
from django.dispatch import Signal
from django.utils import timezone as tz

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from events.capacity import lock_event
from events.constants import (
    EventState,
    SignupAction,
    SignupStatus,
    VoicePresenceSource,
)
from events.ledger import (
    SignupActor,
    record_ready_check_transition,
    record_signup_change,
    snapshot,
)
from events.line import ranks_if_waitlisted, waitlist_rank
from events.models import (
    Event,
    EventSignup,
    EventVoicePresence,
    ReadyCheck,
    ReadyCheckEntry,
    RollCallMode,
    SignupLedgerEntry,
)
from events.ready_check_constants import (
    PRESENCE_FRESH,
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
    end_ready_check_on_completion,
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
    confirm_signup,
    sync_event_roster,
)
from telemetry.logging import get_logger
from tournament.models import Team

__all__ = [
    "CloseResult",
    "ConfirmResult",
    "NotHeldError",
    "OpenResult",
    "READY_CHECK_HELD_MESSAGE",
    "cancel_ready_check",
    "chase_unconfirmed",
    "close_for_start",
    "close_ready_check",
    "confirm_ready",
    "enter_roll_call",
    "escalate_ready_check",
    "live_ready_check",
    "lock_event",
    "open_ready_check",
    "refused_confirm_message",
    "resolve_held_ready_check",
    "staff_confirm_signup",
    "transition_with_ready_check",
    "trusted_present_user_ids",
]

log = get_logger(__name__)

IN_PROGRESS_MESSAGE = "The tournament is already running."
TEAMS_MADE_MESSAGE = "Teams are already made for this event."
REASON_REQUIRED_MESSAGE = "A reason is required."
NOT_HELD_MESSAGE = "The ready check is not held."
UNKNOWN_KEEP_MESSAGE = "Unknown signup in keep list."
READY_CHECK_HELD_MESSAGE: Final = (
    "The ready check is held for staff; resolve it before starting."
)


class NotHeldError(ValueError):
    pass


class ConfirmResult(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_CONFIRMED = "already_confirmed"
    CLOSED = "closed"
    NOT_IN_CHECK = "not_in_check"


@dataclass(frozen=True)
class OpenResult:
    check: ReadyCheck
    created: bool
    roster: RosterSyncResult


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


def trusted_present_user_ids(event: Event, now: datetime) -> set[int]:
    return set(
        EventVoicePresence.objects.filter(
            event=event,
            present=True,
            source=VoicePresenceSource.FEED,
            guild_id=event.organization.discord_server_id or "",
            channel_id=event.event_voice_channel_id,
            last_seen_at__gte=now - PRESENCE_FRESH,
        ).values_list("user_id", flat=True)
    )


def _confirm_voice_present(
    locked: Event,
    check: ReadyCheck,
    entries: Sequence[ReadyCheckEntry],
    now: datetime,
) -> set[int]:
    if check.settings_snapshot.get("voice_presence_confirms") is not True:
        return set()
    pending = [
        entry for entry in entries if entry.state == ReadyCheckEntryState.PENDING
    ]
    if not pending:
        return set()
    present = trusted_present_user_ids(locked, now)
    confirmed: set[int] = set()
    for entry in pending:
        if entry.user_id not in present:
            continue
        result = confirm_ready(
            locked,
            entry.user,
            via=ReadyCheckConfirmVia.VOICE,
            actor=SignupActor.voice(entry.user),
        )
        if result == ConfirmResult.CONFIRMED:
            confirmed.add(entry.user_id)
    return confirmed


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

    ranks = ranks_if_waitlisted(locked, signups)
    for signup in signups:
        record_signup_change(
            event=locked,
            subject=signup.user,
            actor=actor,
            action=SignupAction.READY_CHECK_ASKED,
            signup=signup,
            after=snapshot(signup, waitlist_rank=ranks.get(signup.pk)),
            reason="ready_check_opened",
            correlation_id=correlation_id,
        )

    voice_confirmed = _confirm_voice_present(locked, check, entries, now)
    roster = sync_event_roster(locked)
    invalidate_after_commit(locked, *signups)

    pending_user_ids = tuple(
        entry.user_id
        for entry in entries
        if entry.state == ReadyCheckEntryState.PENDING
        and entry.user_id not in voice_confirmed
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
            "voice_confirmed": len(voice_confirmed),
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
        "voice_confirmed": len(voice_confirmed),
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
    caused_by: SignupLedgerEntry | None = None,
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

    rank = waitlist_rank(signup)
    before = snapshot(signup, waitlist_rank=rank)
    entry_changed = False
    if entry.state == ReadyCheckEntryState.PENDING:
        staff_on_held = (
            via == ReadyCheckConfirmVia.STAFF and check.phase == ReadyCheckPhase.HELD
        )
        if (
            via == ReadyCheckConfirmVia.STAFF
            and check.phase == ReadyCheckPhase.CLOSED
            and signup.status == SignupStatus.APPROVED
        ):
            _confirm_after_close(locked, check, signup, actor=actor)
            return ConfirmResult.CONFIRMED
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
        after=snapshot(signup, waitlist_rank=rank),
        reason="ready_check_confirmed",
        caused_by=caused_by,
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
    seat: bool = False,
) -> list[EventSignup]:
    seated: list[EventSignup] = []
    ranks = ranks_if_waitlisted(locked, [entry.signup for entry in entries])
    for entry in entries:
        signup = entry.signup
        rank = ranks.get(signup.pk) if signup is not None else None
        before = (
            snapshot(signup, waitlist_rank=rank)
            if seat and signup is not None
            else None
        )
        if seat and signup is not None and _sync_signup_confirmed(locked, signup):
            seated.append(signup)
        record_signup_change(
            event=locked,
            subject=entry.user,
            actor=actor,
            action=action,
            signup=signup,
            before=before,
            after=snapshot(signup, waitlist_rank=rank) if signup is not None else None,
            reason=reason,
            correlation_id=correlation_id,
        )
    return seated


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
    first_drop: SignupLedgerEntry | None = None
    ranks = ranks_if_waitlisted(locked, [entry.signup for entry in entries])
    dropped_ranks: list[int] = []
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
        rank = ranks.get(signup.pk)
        if rank is not None:
            dropped_ranks.append(rank)
            rank -= sum(1 for gone in dropped_ranks if gone < rank)
        before = snapshot(signup, waitlist_rank=rank)
        signup.status = SignupStatus.DROPPED
        signup.waitlist_position = None
        signup.event = locked
        ReadyCheckEntry.objects.filter(pk=entry.pk).update(
            state=ReadyCheckEntryState.DROPPED, dropped_at=now
        )
        entry.state = ReadyCheckEntryState.DROPPED
        entry.dropped_at = now
        _roster_remove_if_left(signup)
        row = record_signup_change(
            event=locked,
            subject=entry.user,
            actor=actor,
            action=SignupAction.DROPPED,
            signup=signup,
            before=before,
            after=snapshot(signup, waitlist_rank=None),
            reason=reason,
            correlation_id=correlation_id,
        )
        first_drop = first_drop or row
        dropped_user_ids.append(entry.user_id)
        dropped_signups.append(signup)
    promoted_signup_ids: list[int] = []
    if dropped_signups and locked.max_players:
        promoted_signup_ids = [
            promoted.pk
            for promoted in _promote_from_waitlist(
                locked, cause=first_drop, actor=actor
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
        dropped_user_ids, promoted_signup_ids = _drop(
            locked, check, droppable, actor=actor, step=step
        )
        member_rows = (
            SignupAction.READY_CHECK_KEPT,
            "signup_confirmed",
            _pending(active),
        )
    elif low_action == ReadyCheckLowCompletionAction.HOLD_FOR_STAFF:
        step = "hold"
        phase, outcome = ReadyCheckPhase.HELD, ""
        member_rows = (SignupAction.READY_CHECK_HELD, "held_for_staff", droppable)
    else:
        phase, outcome = ReadyCheckPhase.CLOSED, ReadyCheckOutcome.NON_BINDING
        member_rows = (SignupAction.READY_CHECK_KEPT, "non_binding", pending)

    action, reason, entries = member_rows
    seated = _record_member_rows(
        locked,
        entries,
        actor=actor,
        action=action,
        reason=reason,
        correlation_id=f"rc{check.pk}:{step}",
        seat=outcome == ReadyCheckOutcome.NON_BINDING,
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
        "seated": len(seated),
    }
    record_ready_check_transition(
        event=locked, actor=actor, check=check, step=step, extra=counts
    )
    if dropped_user_ids or promoted_signup_ids or seated:
        invalidate_after_commit(locked, *seated)
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


def _excuse(entries: Sequence[ReadyCheckEntry]) -> None:
    ReadyCheckEntry.objects.filter(
        pk__in=[entry.pk for entry in entries], state=ReadyCheckEntryState.PENDING
    ).update(state=ReadyCheckEntryState.EXCUSED)
    for entry in entries:
        entry.state = ReadyCheckEntryState.EXCUSED


@transaction.atomic
def resolve_held_ready_check(
    event: Event,
    *,
    actor: SignupActor,
    apply_drops: bool,
    keep_signup_ids: Collection[int],
    reason: str,
) -> CloseResult:
    reason = reason.strip()
    if not reason:
        raise ValueError(REASON_REQUIRED_MESSAGE)
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None:
        return CloseResult(check=None, changed=False)
    if locked.state != EventState.ROLL_CALL:
        return CloseResult(check=check, changed=False)
    if check.phase != ReadyCheckPhase.HELD:
        raise NotHeldError(NOT_HELD_MESSAGE)

    keep = set(keep_signup_ids)
    known = set(
        check.entries.filter(signup_id__in=keep).values_list("signup_id", flat=True)
    )
    if keep - known:
        raise ValueError(UNKNOWN_KEEP_MESSAGE)

    step = "resolve"
    correlation_id = f"rc{check.pk}:{step}"
    active, droppable = _active_and_droppable(check)
    pending = _pending(active)
    dropped_user_ids: list[int] = []
    promoted_signup_ids: list[int] = []
    if apply_drops:
        excused = [entry for entry in droppable if entry.signup_id in keep]
        to_drop = [entry for entry in droppable if entry.signup_id not in keep]
        _excuse(excused)
        dropped_user_ids, promoted_signup_ids = _drop(
            locked, check, to_drop, actor=actor, step=step, reason=reason
        )
        kept = [
            entry for entry in pending if entry.state != ReadyCheckEntryState.DROPPED
        ]
    else:
        excused = pending
        _excuse(excused)
        kept = pending
    seated = _record_member_rows(
        locked,
        kept,
        actor=actor,
        action=SignupAction.READY_CHECK_KEPT,
        reason=reason,
        correlation_id=correlation_id,
        seat=True,
    )

    confirmed = sum(
        1 for entry in active if entry.state == ReadyCheckEntryState.CONFIRMED
    )
    completion_pct = confirmed * 100 // len(active) if active else 100
    now = tz.now()
    ReadyCheck.objects.filter(pk=check.pk).update(
        phase=ReadyCheckPhase.CLOSED,
        outcome=ReadyCheckOutcome.STAFF_RESOLVED,
        completion_pct=completion_pct,
        closed_at=now,
        last_progress_at=now,
        resolved_by=actor.user,
        resolve_reason=reason,
    )
    check.refresh_from_db()

    counts: dict[str, Any] = {
        "mode": check_mode(check),
        "apply_drops": apply_drops,
        "completion_pct": completion_pct,
        "active": len(active),
        "confirmed": confirmed,
        "pending": len(pending),
        "excused": len(excused),
        "dropped": len(dropped_user_ids),
        "promoted": len(promoted_signup_ids),
        "seated": len(seated),
    }
    record_ready_check_transition(
        event=locked, actor=actor, check=check, step=step, reason=reason, extra=counts
    )
    if dropped_user_ids or promoted_signup_ids or seated:
        invalidate_after_commit(locked, *seated)
        locked.refresh_signup_post_on_commit()

    send_on_commit(
        ready_check_closed,
        _change(check, [entry.user_id for entry in pending], actor),
    )
    if dropped_user_ids:
        send_on_commit(
            ready_check_member_dropped, _change(check, dropped_user_ids, actor)
        )
    _log_on_commit(
        "ready_check_resolved",
        {
            "event_id": locked.pk,
            "ready_check_id": check.pk,
            "phase": check.phase,
            "outcome": check.outcome,
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


@transaction.atomic
def close_for_start(event: Event, *, actor: SignupActor) -> bool:
    """False when a held ready check blocks the start."""
    locked = lock_event(event)
    check = live_ready_check(locked, lock=True)
    if check is None or check.phase == ReadyCheckPhase.CLOSED:
        return True
    if check.phase == ReadyCheckPhase.HELD:
        _log_on_commit(
            "ready_check_start_blocked",
            {
                "event_id": locked.pk,
                "ready_check_id": check.pk,
                "phase": check.phase,
                "actor_user_id": _actor_user_id(actor),
            },
        )
        return False
    result = close_ready_check(locked, actor=actor)
    return result.check is None or result.check.phase != ReadyCheckPhase.HELD


@transaction.atomic
def staff_confirm_signup(signup: EventSignup, *, actor: SignupActor) -> EventSignup:
    locked = lock_event(signup.event)
    check = live_ready_check(locked, lock=True)
    if (
        check is not None
        and check.phase != ReadyCheckPhase.CLOSED
        and check.entries.filter(signup_id=signup.pk).exists()
    ):
        result = confirm_ready(
            locked, signup.user, via=ReadyCheckConfirmVia.STAFF, actor=actor
        )
        if result in (ConfirmResult.CONFIRMED, ConfirmResult.ALREADY_CONFIRMED):
            return (
                EventSignup.objects.nocache()
                .select_related("user", "event")
                .get(pk=signup.pk)
            )

    if check is not None and check.phase == ReadyCheckPhase.CLOSED:
        _confirm_after_close(locked, check, signup, actor=actor)
        return signup
    confirm_signup(
        signup,
        actor=actor,
        reason="staff_confirmed",
        correlation_id=f"rc{check.pk}:confirm" if check is not None else "",
    )
    return signup


def _confirm_after_close(
    locked: Event, check: ReadyCheck, signup: EventSignup, *, actor: SignupActor
) -> None:
    confirm_signup(
        signup,
        actor=actor,
        reason="staff_confirmed",
        rules_overridden=["ready_check_closed"],
        correlation_id=f"rc{check.pk}:confirm",
    )
    _log_on_commit(
        "ready_check_staff_confirm_after_close",
        {
            "event_id": locked.pk,
            "ready_check_id": check.pk,
            "phase": check.phase,
            "outcome": check.outcome,
            "signup_id": signup.pk,
            "actor_user_id": _actor_user_id(actor),
        },
    )


@transaction.atomic
def enter_roll_call(event: Event, *, actor: SignupActor) -> RosterSyncResult:
    """Open the ready check; with teams already made, enter roll call without one."""
    locked = lock_event(event)
    if (
        locked.state == EventState.SIGNUPS_OPEN
        and _teams_made(locked)
        and live_ready_check(locked) is None
    ):
        locked.transition_state(EventState.ROLL_CALL)
        event.state = locked.state
        synced = sync_event_roster(locked)
        _log_on_commit(
            "ready_check_skipped_teams_made",
            {"event_id": locked.pk, "actor_user_id": _actor_user_id(actor)},
        )
        return synced
    return open_ready_check(event, actor=actor).roster


_TRANSITION_CANCEL_REASONS: Final[dict[str, str]] = {
    EventState.SIGNUPS_OPEN: "reopened",
    EventState.CANCELLED: "event_cancelled",
}


@transaction.atomic
def transition_with_ready_check(
    event: Event, new_state: str, *, actor: SignupActor
) -> bool:
    """Move the event to new_state, keeping its ready check in step.

    False when a held ready check blocks the start; the hold is kept.
    """
    if new_state == EventState.ROLL_CALL and event.state != EventState.ROLL_CALL:
        enter_roll_call(event, actor=actor)
        return True
    if event.state == EventState.ROLL_CALL:
        if new_state == EventState.IN_PROGRESS:
            if not close_for_start(event, actor=actor):
                return False
        elif new_state == EventState.COMPLETED:
            end_ready_check_on_completion(event, actor=actor)
        elif new_state in _TRANSITION_CANCEL_REASONS:
            cancel_ready_check(
                event, actor=actor, reason=_TRANSITION_CANCEL_REASONS[new_state]
            )
    event.transition_state(new_state)
    return True
