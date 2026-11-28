from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone as tz
from structlog.contextvars import get_contextvars

from events.constants import (
    ActorRole,
    SignupAction,
    SignupMeans,
    SignupStatus,
    StaffReasonPolicy,
)
from events.models import Event, EventSignup, ReadyCheck, SignupLedgerEntry
from events.overrides import StaffReasonRequired
from events.permissions import has_event_staff_access
from events.ready_check_constants import REMOVED_SIGNUP_STATUSES
from events.schemas import SignupSnapshot
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import CustomUser

__all__ = [
    "PLACEMENT_ACTIONS",
    "REMOVED_STATUS_FOR",
    "RESTORABLE_ACTIONS",
    "ActorRole",
    "SignupAction",
    "SignupActor",
    "SignupMeans",
    "current_interaction_id",
    "event_snapshot",
    "is_placement",
    "latest_restorable_withdrawal",
    "restorable_withdrawals",
    "record_ready_check_transition",
    "record_signup_change",
    "require_staff_reason",
    "snapshot",
    "user_snapshot",
]

log = get_logger(__name__)

PLACEMENT_ACTIONS: frozenset[str] = frozenset(
    {
        SignupAction.STAFF_ADDED,
        SignupAction.DEMOTED,
        SignupAction.REINSTATED,
        SignupAction.VOIDED_WITHDRAWAL,
        SignupAction.TRANSFERRED_OUT,
        SignupAction.TRANSFERRED_IN,
        SignupAction.SWAPPED,
    }
)

REMOVED_STATUS_FOR: dict[str, str] = {
    SignupAction.WITHDREW: SignupStatus.CANCELLED,
    SignupAction.DECLINED: SignupStatus.CANCELLED,
    SignupAction.REJECTED: SignupStatus.REJECTED,
}

RESTORABLE_ACTIONS: frozenset[str] = frozenset(REMOVED_STATUS_FOR)

_PLACE_HANDOFF_ACTIONS: frozenset[str] = frozenset(
    {SignupAction.MOVED_EVENT, SignupAction.TRANSFERRED_OUT}
)

CORRELATION_ID_MAX_LENGTH = 64


def current_interaction_id() -> str:
    return str(get_contextvars().get("interaction_id") or "")[
        :CORRELATION_ID_MAX_LENGTH
    ]


@dataclass(frozen=True)
class SignupActor:
    user: CustomUser | None
    role: ActorRole
    means: SignupMeans
    correlation_id: str = ""
    staff_power: bool = False

    @classmethod
    def system(cls, *, correlation_id: str = "") -> SignupActor:
        return cls(
            user=None,
            role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            correlation_id=correlation_id,
        )

    @classmethod
    def voice(cls, user: CustomUser, *, correlation_id: str = "") -> SignupActor:
        return cls(
            user=user,
            role=ActorRole.MEMBER,
            means=SignupMeans.DISCORD_VOICE,
            correlation_id=correlation_id,
        )

    @classmethod
    def from_request(
        cls, request: HttpRequest, *, role: ActorRole = ActorRole.MEMBER
    ) -> SignupActor:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            user = None
        return cls(user=user, role=role, means=SignupMeans.WEB)

    @classmethod
    def discord(
        cls,
        user: CustomUser,
        *,
        means: SignupMeans = SignupMeans.DISCORD_BUTTON,
        role: ActorRole = ActorRole.MEMBER,
        correlation_id: str | None = None,
    ) -> SignupActor:
        return cls(
            user=user,
            role=role,
            means=means,
            correlation_id=(
                current_interaction_id() if correlation_id is None else correlation_id
            ),
        )

    @classmethod
    def for_request_on(
        cls,
        request: HttpRequest,
        subject: CustomUser,
        event: Event,
        *,
        staff_only: bool = False,
    ) -> SignupActor:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return cls(user=None, role=ActorRole.MEMBER, means=SignupMeans.WEB)
        is_self = user.pk == subject.pk
        is_staff = has_event_staff_access(user, event)
        return cls(
            user=user,
            role=ActorRole.STAFF if is_staff and not is_self else ActorRole.MEMBER,
            means=SignupMeans.WEB,
            staff_power=staff_only and is_staff and is_self,
        )


def is_placement(action: str, *, from_status: str | None = None) -> bool:
    if action in PLACEMENT_ACTIONS:
        return True
    return action == SignupAction.APPROVED and from_status == SignupStatus.WAITLISTED


def require_staff_reason(
    *,
    event_id: int,
    policy: str,
    actor: SignupActor,
    subject_id: int,
    action: str,
    from_status: str | None,
    reason: str,
) -> str:
    """Return the trimmed reason; raise StaffReasonRequired when the policy needs one."""
    trimmed = reason.strip()
    if (
        trimmed
        or actor.role != ActorRole.STAFF
        or actor.user is None
        or actor.user.pk == subject_id
        or policy == StaffReasonPolicy.OPTIONAL
    ):
        return trimmed
    placement = is_placement(action, from_status=from_status)
    if policy == StaffReasonPolicy.PLACEMENTS and not placement:
        return trimmed
    log.warning(
        "staff_reason_refused",
        system="events",
        subsystem="staff_reason",
        event_id=event_id,
        actor_id=actor.user.pk,
        subject_id=subject_id,
        action=action,
        from_status=from_status,
        placement=placement,
        policy=policy,
    )
    raise StaffReasonRequired()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


_UNSET: Any = object()


def snapshot(
    signup: EventSignup,
    *,
    extra: dict[str, Any] | None = None,
    waitlist_rank: int | None = _UNSET,
) -> SignupSnapshot:
    return SignupSnapshot(
        status=signup.status,
        commitment=signup.commitment,
        rsvp_class=signup.rsvp_class,
        signed_up_at=signup.signed_up_at,
        line_seq=signup.line_seq,
        waitlist_position=(
            signup.waitlist_position if waitlist_rank is _UNSET else waitlist_rank
        ),
        event_team_id=signup.event_team_id,
        extra=dict(extra) if extra else {},
    )


def _after_status(entry: SignupLedgerEntry) -> str | None:
    if entry.after is not None and entry.after.get("status"):
        return str(entry.after["status"])
    return REMOVED_STATUS_FOR.get(entry.action)


def _restorable_in(
    signup: EventSignup, entries: Sequence[SignupLedgerEntry]
) -> SignupLedgerEntry | None:
    """``entries`` are this signup's ledger entries, newest first."""
    index = next(
        (i for i, e in enumerate(entries) if e.action in RESTORABLE_ACTIONS), None
    )
    if index is None:
        return None
    candidate = entries[index]
    if candidate.before is None:
        return None
    if candidate.before.get("status") in REMOVED_SIGNUP_STATUSES:
        return None
    removed_status = _after_status(candidate)
    if removed_status != signup.status:
        return None
    for later in entries[:index]:
        if later.action in _PLACE_HANDOFF_ACTIONS:
            return None
        later_status = (later.after or {}).get("status")
        if later_status is not None and later_status != removed_status:
            return None
    return candidate


def _signup_entries(signups: Sequence[EventSignup]) -> QuerySet[SignupLedgerEntry]:
    return SignupLedgerEntry.objects.filter(
        signup__in=[s.pk for s in signups]
    ).order_by("-occurred_at", "-pk")


def latest_restorable_withdrawal(signup: EventSignup) -> SignupLedgerEntry | None:
    """The withdrawal, decline or rejection that still describes the row, if any."""
    entries = _signup_entries([signup]).filter(
        event_id=signup.event_id, subject_user_id=signup.user_id
    )
    return _restorable_in(signup, list(entries))


def restorable_withdrawals(
    signups: Sequence[EventSignup],
) -> dict[int, SignupLedgerEntry | None]:
    """``latest_restorable_withdrawal`` for many signups in one query."""
    by_signup: dict[int, list[SignupLedgerEntry]] = {s.pk: [] for s in signups}
    keys = {s.pk: (s.event_id, s.user_id) for s in signups}
    if signups:
        for entry in _signup_entries(signups):
            if keys[entry.signup_id] == (entry.event_id, entry.subject_user_id):
                by_signup[entry.signup_id].append(entry)
    return {s.pk: _restorable_in(s, by_signup[s.pk]) for s in signups}


def event_snapshot(event: Event) -> dict[str, Any]:
    return {
        "id": event.pk,
        "name": event.name,
        "scheduled_at": _iso(event.scheduled_at),
        "ends_at": _iso(event.ends_at),
        "state": event.state,
        "organization_id": event.organization_id,
        "series_id": event.event_repeater_id,
        "tournament_id": event.tournament_id,
    }


def user_snapshot(user: CustomUser | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "user_id": user.pk,
        "username": user.username,
        "nickname": user.nickname,
        "discord_id": user.discordId,
    }


def _dump(value: SignupSnapshot | None) -> dict[str, Any] | None:
    return value.model_dump(mode="json") if value is not None else None


def record_signup_change(
    *,
    event: Event,
    subject: CustomUser,
    actor: SignupActor,
    action: SignupAction,
    signup: EventSignup | None = None,
    before: SignupSnapshot | None = None,
    after: SignupSnapshot | None = None,
    reason: str = "",
    rules_overridden: Sequence[str] = (),
    caused_by: SignupLedgerEntry | None = None,
    correlation_id: str = "",
    occurred_at: datetime | None = None,
) -> SignupLedgerEntry:
    if actor.staff_power and after is not None:
        after = after.model_copy(update={"extra": {**after.extra, "staff_power": True}})
    entry = SignupLedgerEntry.objects.create(
        event=event,
        organization_id=event.organization_id,
        signup=signup,
        event_snapshot=event_snapshot(event),
        subject_user=subject,
        subject_snapshot=user_snapshot(subject),
        actor_user=actor.user,
        actor_snapshot=user_snapshot(actor.user),
        actor_role=actor.role,
        means=actor.means,
        on_behalf=actor.user is not None and actor.user.pk != subject.pk,
        action=action,
        before=_dump(before),
        after=_dump(after),
        reason=reason,
        rules_overridden=list(rules_overridden),
        caused_by=caused_by,
        correlation_id=correlation_id or actor.correlation_id,
        occurred_at=occurred_at if occurred_at is not None else tz.now(),
    )
    fields: dict[str, Any] = {
        "entry_id": entry.pk,
        "event_id": entry.event_id,
        "signup_id": entry.signup_id,
        "subject_user_id": entry.subject_user_id,
        "actor_user_id": entry.actor_user_id,
        "actor_role": str(entry.actor_role),
        "means": str(entry.means),
        "action": str(entry.action),
        "correlation_id": entry.correlation_id,
    }
    transaction.on_commit(
        lambda: log.info(
            "signup_ledger_entry_recorded",
            system="events",
            subsystem="ledger",
            **fields,
        )
    )
    return entry


def record_ready_check_transition(
    *,
    event: Event,
    actor: SignupActor,
    check: ReadyCheck,
    step: str,
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> SignupLedgerEntry:
    entry = SignupLedgerEntry.objects.create(
        event=event,
        organization_id=event.organization_id,
        signup=None,
        event_snapshot=event_snapshot(event),
        subject_user=None,
        subject_snapshot={},
        actor_user=actor.user,
        actor_snapshot=user_snapshot(actor.user),
        actor_role=actor.role,
        means=actor.means,
        on_behalf=False,
        action=SignupAction.READY_CHECK_TRANSITION,
        before=None,
        after={
            "extra": {
                "step": step,
                "phase": check.phase,
                "outcome": check.outcome,
                **(extra or {}),
            }
        },
        reason=reason or step,
        correlation_id=f"rc{check.pk}:{step}",
        occurred_at=tz.now(),
    )
    fields: dict[str, Any] = {
        "entry_id": entry.pk,
        "event_id": entry.event_id,
        "ready_check_id": check.pk,
        "step": step,
        "phase": check.phase,
        "outcome": check.outcome,
        "actor_user_id": entry.actor_user_id,
        "actor_role": str(entry.actor_role),
        "means": str(entry.means),
        "action": str(entry.action),
        "correlation_id": entry.correlation_id,
    }
    transaction.on_commit(
        lambda: log.info(
            "signup_ledger_entry_recorded",
            system="events",
            subsystem="ledger",
            **fields,
        )
    )
    return entry
