from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone as tz

from events.constants import ActorRole, SignupAction, SignupMeans
from events.models import Event, EventSignup, SignupLedgerEntry
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
    "event_snapshot",
    "record_signup_change",
    "snapshot",
    "user_snapshot",
]

log = get_logger(__name__)

PLACEMENT_ACTIONS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SignupActor:
    user: CustomUser | None
    role: ActorRole
    means: SignupMeans

    @classmethod
    def system(cls) -> SignupActor:
        return cls(user=None, role=ActorRole.SYSTEM, means=SignupMeans.SYSTEM)

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
    ) -> SignupActor:
        return cls(user=user, role=role, means=means)


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
        correlation_id=correlation_id,
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
