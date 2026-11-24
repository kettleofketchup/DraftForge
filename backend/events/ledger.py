from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone as tz
from structlog.contextvars import get_contextvars

from events.constants import ActorRole, SignupAction, SignupMeans
from events.models import Event, EventSignup, ReadyCheck, SignupLedgerEntry
from events.permissions import has_event_staff_access
from events.schemas import SignupSnapshot
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import CustomUser

__all__ = [
    "PLACEMENT_ACTIONS",
    "ActorRole",
    "SignupAction",
    "SignupActor",
    "SignupMeans",
    "current_interaction_id",
    "event_snapshot",
    "record_ready_check_transition",
    "record_signup_change",
    "snapshot",
    "user_snapshot",
]

log = get_logger(__name__)

PLACEMENT_ACTIONS: frozenset[str] = frozenset()

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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def snapshot(
    signup: EventSignup, *, extra: dict[str, Any] | None = None
) -> SignupSnapshot:
    return SignupSnapshot(
        status=signup.status,
        commitment=signup.commitment,
        rsvp_class=signup.rsvp_class,
        signed_up_at=signup.signed_up_at,
        line_seq=signup.line_seq,
        waitlist_position=signup.waitlist_position,
        event_team_id=signup.event_team_id,
        extra=dict(extra) if extra else {},
    )


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
