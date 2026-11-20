"""Roster snapshots and TeamLog row writing shared by the signal, service and PATCH."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.models import CustomUser, Team, TeamLog, Tournament

if TYPE_CHECKING:
    from events.models import Event


def _sorted_ids(manager: Any) -> list[int]:
    return sorted(manager.nocache().values_list("pk", flat=True))


def roster_snapshot(team: Team) -> dict[str, Any]:
    return {
        "name": team.name,
        "captain_id": team.captain_id,
        "deputy_captain_id": team.deputy_captain_id,
        "member_ids": _sorted_ids(team.members),
        "dropin_ids": _sorted_ids(team.dropin_members),
        "left_ids": _sorted_ids(team.left_members),
    }


def source_event(tournament: Tournament | None) -> Event | None:
    if tournament is None:
        return None
    return tournament.source_event.nocache().order_by("pk").first()


def log_snapshot_fields(team: Team) -> dict[str, Any]:
    """TeamLog columns that must survive the team: capture before any delete."""
    tournament = team.tournament
    event = source_event(tournament)
    organization_id: int | None = None
    occasion_at: datetime | None = None
    if event is not None:
        organization_id = event.organization_id
        occasion_at = event.ends_at or event.scheduled_at
    if tournament is not None:
        if organization_id is None and tournament.league is not None:
            organization_id = tournament.league.organization_id
        if occasion_at is None:
            occasion_at = tournament.date_played
    return {
        "team_snapshot_id": team.pk,
        "tournament_id": team.tournament_id,
        "event_id": event.pk if event is not None else None,
        "organization_id": organization_id,
        "occasion_at": occasion_at,
        "team_name": team.name,
    }


def write_team_log(
    team: Team | None,
    *,
    snapshot: dict[str, Any],
    action: str,
    via: str,
    actor: CustomUser | None = None,
    target_user: CustomUser | None = None,
    reason: str = "",
    override_rules: list[str] | None = None,
    details: dict[str, Any],
) -> TeamLog:
    return TeamLog.objects.create(
        team=team,
        **snapshot,
        actor=actor,
        via=via,
        action=action,
        target_user=target_user,
        reason=reason,
        override_rules=list(override_rules or []),
        details=details,
    )
