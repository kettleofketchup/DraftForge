"""Readers for the production tournament API payloads used by the prod sync commands.

Current payloads reference users by pk into a ``_users`` dict and teams by pk;
older ones nested the serialized user or team. Both shapes are accepted.
"""

from datetime import datetime, time
from datetime import timezone as dt_timezone
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from app.models import Team

UserRef = dict[str, Any] | int | str | None
TeamRef = dict[str, Any] | int | None


def parse_date_played(value: str | None) -> datetime:
    if value:
        parsed = parse_datetime(value)
        if parsed is None:
            day = parse_date(value)
            parsed = datetime.combine(day, time.min) if day else None
        if parsed is not None:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, dt_timezone.utc)
            return parsed
    return timezone.now()


def index_users(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(pk): user for pk, user in (data.get("_users") or {}).items()}


def resolve_user(
    ref: UserRef, users: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    if ref is None or isinstance(ref, dict):
        return ref
    return users.get(str(ref))


class TeamLookup:
    """Local teams keyed by their production pk, falling back to name."""

    def __init__(self) -> None:
        self.by_pk: dict[int, Team] = {}
        self.by_name: dict[str, Team] = {}

    def add(self, team_data: dict[str, Any], team: Team) -> None:
        if isinstance(team_data.get("pk"), int):
            self.by_pk[team_data["pk"]] = team
        self.by_name[team.name] = team

    def get(self, ref: TeamRef) -> Team | None:
        if ref is None:
            return None
        if isinstance(ref, dict):
            pk, name = ref.get("pk"), ref.get("name")
            team = self.by_pk.get(pk) if isinstance(pk, int) else None
            return team or (self.by_name.get(name) if name else None)
        return self.by_pk.get(ref)
