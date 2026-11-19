"""team_roster_changed signal and the audit-owner context for team roster writes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.db import transaction
from django.dispatch import Signal

from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import TeamLog

log = get_logger(__name__)

team_roster_changed: Signal = Signal()

# True while a caller (service or serializer) writes its own TeamLog rows,
# so the m2m signal handler skips its via=system rows.
team_audit_owner: ContextVar[bool] = ContextVar("team_audit_owner", default=False)


@dataclass(frozen=True)
class TeamRosterChange:
    log_id: int
    team_id: int | None
    tournament_id: int | None
    event_id: int | None
    action: str
    via: str
    actor_id: int | None
    target_user_id: int | None
    replacing_user_id: int | None
    reason: str
    override_codes: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)


@contextmanager
def owning_team_audit() -> Iterator[None]:
    token = team_audit_owner.set(True)
    try:
        yield
    finally:
        team_audit_owner.reset(token)


def change_from_log(team_log: TeamLog) -> TeamRosterChange:
    details: dict[str, Any] = team_log.details or {}
    return TeamRosterChange(
        log_id=team_log.pk,
        team_id=team_log.team_id,
        tournament_id=team_log.tournament_id,
        event_id=team_log.event_id,
        action=team_log.action,
        via=team_log.via,
        actor_id=team_log.actor_id,
        target_user_id=team_log.target_user_id,
        replacing_user_id=details.get("replacing_user_id"),
        reason=team_log.reason,
        override_codes=list(team_log.override_rules or []),
        before=dict(details.get("before") or {}),
        after=dict(details.get("after") or {}),
    )


def _receiver_name(receiver: Any) -> str:
    return getattr(receiver, "__qualname__", None) or repr(receiver)


def send_roster_changed_on_commit(change: TeamRosterChange) -> None:
    def _send() -> None:
        sender = apps.get_model("app", "Team")
        results = team_roster_changed.send_robust(sender=sender, change=change)
        for receiver, result in results:
            if isinstance(result, Exception):
                log.error(
                    "team_roster_listener_failed",
                    system="tournament",
                    subsystem="teams",
                    log_id=change.log_id,
                    receiver=_receiver_name(receiver),
                    error=repr(result),
                )

    transaction.on_commit(_send)
