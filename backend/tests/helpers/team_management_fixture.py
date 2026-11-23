"""Playwright fixture for the team management dialog (#546).

Not covered by the test-db hash: the tournament is built on demand through
``/api/tests/reset-tournament/team_management/``.
"""

from datetime import date

from app.models import CustomUser
from league.models import League
from tests.populate.constants import DTX_STEAM_LEAGUE_ID
from tournament.models import Team, Tournament

TEAM_MANAGEMENT_TOURNAMENT_NAME: str = "Team Management Tournament"
TEAM_MANAGEMENT_USER_PREFIX: str = "tm_fixture_"
TEAM_MANAGEMENT_SEARCH_TARGET: str = f"{TEAM_MANAGEMENT_USER_PREFIX}searchable"
TEAM_MANAGEMENT_GHOST: str = f"{TEAM_MANAGEMENT_USER_PREFIX}ghost"
TEAM_MANAGEMENT_DELTA_CAPTAIN: str = f"{TEAM_MANAGEMENT_USER_PREFIX}delta_1"
TEAM_MANAGEMENT_DELTA_PLACEMENT: int = 4
CAPTAIN_TAKEOVER_TOURNAMENT_NAME: str = "Captain Takeover Tournament"


def _user(suffix: str) -> CustomUser:
    user, _ = CustomUser.objects.get_or_create(
        username=f"{TEAM_MANAGEMENT_USER_PREFIX}{suffix}"
    )
    return user


def _roster(key: str) -> list[CustomUser]:
    return [_user(f"{key}_{n}") for n in range(1, 6)]


def populate_team_management_tournament(
    force: bool = False, name: str = TEAM_MANAGEMENT_TOURNAMENT_NAME
) -> Tournament:
    """TM Alpha (captain + deputy), TM Bravo (one stand-in), TM Ghost (ghost
    captain), TM Delta (eliminated, placement 4)."""
    league = League.objects.select_related("organization").get(
        steam_league_id=DTX_STEAM_LEAGUE_ID
    )
    existing = Tournament.objects.filter(name=name)
    if existing.exists():
        if not force:
            return existing.first()
        existing.delete()

    alpha = _roster("alpha")
    bravo = _roster("bravo")
    bravo_standin = _user("bravo_standin")
    ghost_roster = _roster("charlie")
    ghost = _user("ghost")
    delta = _roster("delta")
    search_target = _user("searchable")

    tournament = Tournament.objects.create(
        name=name,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )
    tournament.users.add(
        *alpha, *bravo, bravo_standin, *ghost_roster, ghost, *delta, search_target
    )

    alpha_team = Team.objects.create(
        tournament=tournament,
        name="TM Alpha",
        captain=alpha[0],
        deputy_captain=alpha[1],
        draft_order=1,
    )
    alpha_team.members.set(alpha)

    bravo_team = Team.objects.create(
        tournament=tournament, name="TM Bravo", captain=bravo[0], draft_order=2
    )
    bravo_team.members.set(bravo)
    bravo_team.dropin_members.add(bravo_standin)

    ghost_team = Team.objects.create(
        tournament=tournament,
        name="TM Ghost",
        captain=ghost_roster[0],
        draft_order=3,
    )
    ghost_team.members.set(ghost_roster)
    Team.objects.filter(pk=ghost_team.pk).invalidated_update(captain=ghost)

    delta_team = Team.objects.create(
        tournament=tournament,
        name="TM Delta",
        captain=delta[0],
        draft_order=4,
        placement=TEAM_MANAGEMENT_DELTA_PLACEMENT,
    )
    delta_team.members.set(delta)

    return Tournament.objects.get(pk=tournament.pk)


def populate_captain_takeover_tournament(force: bool = False) -> Tournament:
    """The team management fixture under its own name, so the captain takeover
    spec never resets the tournament 06-team-management is using."""
    return populate_team_management_tournament(
        force=force, name=CAPTAIN_TAKEOVER_TOURNAMENT_NAME
    )
