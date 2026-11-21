from typing import Literal

from django.db.models import QuerySet

from app.models import CustomUser, Team, Tournament
from app.permissions_tournament import can_edit_tournament
from draft.models import Draft, HeroDraft

Role = Literal["captain", "player", "staff", "spectator"]
DraftKind = Literal["hero", "team"]


def _draft_teams(
    kind: DraftKind, draft_id: int
) -> tuple[QuerySet[Team], Tournament | None] | None:
    if kind == "hero":
        hero = (
            HeroDraft.objects.nocache()
            .select_related("game__tournament__league")
            .filter(pk=draft_id)
            .first()
        )
        if hero is None:
            return None
        teams = Team.objects.nocache().filter(hero_draft_teams__draft_id=draft_id)
        return teams, hero.game.tournament
    draft = (
        Draft.objects.nocache()
        .select_related("tournament__league")
        .filter(pk=draft_id)
        .first()
    )
    if draft is None:
        return None
    if draft.tournament_id is None:
        return Team.objects.none(), None
    return Team.objects.nocache().filter(tournament_id=draft.tournament_id), (
        draft.tournament
    )


def draft_role(user: CustomUser, kind: DraftKind, draft_id: int) -> Role:
    found = _draft_teams(kind, draft_id)
    if found is None:
        return "spectator"
    teams, tournament = found
    if teams.filter(captain_id=user.pk).exists():
        return "captain"
    if teams.filter(members=user).exists():
        return "player"
    if tournament is not None and can_edit_tournament(user, tournament):
        return "staff"
    return "spectator"


def involves_user(role: Role) -> bool:
    return role in ("captain", "player")
