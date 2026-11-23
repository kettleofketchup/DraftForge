"""Playwright fixture for removing team captains from a tournament's players (#841).

Not covered by the test-db hash: the tournament is built on demand through
``/api/tests/reset-tournament/captain_removal/``.
"""

from datetime import date

from app.models import CustomUser, Game, Team, Tournament
from league.models import League
from tests.populate.constants import DTX_STEAM_LEAGUE_ID

CAPTAIN_REMOVAL_TOURNAMENT_NAME: str = "Captain Removal Tournament"
CAPTAIN_REMOVAL_USER_PREFIX: str = "cr_fixture_"
CAPTAIN_REMOVAL_PLAYED_TEAM: str = "CR Knocked Out"
CAPTAIN_REMOVAL_FRESH_TEAM: str = "CR Fresh"


def _user(suffix: str) -> CustomUser:
    user, _ = CustomUser.objects.get_or_create(
        username=f"{CAPTAIN_REMOVAL_USER_PREFIX}{suffix}"
    )
    return user


def _roster(key: str) -> list[CustomUser]:
    return [_user(f"{key}_{n}") for n in range(1, 6)]


def populate_captain_removal_tournament(force: bool = False) -> Tournament:
    """CR Knocked Out (placement 3, lost a game) and CR Fresh (captain only, pre-draft)."""
    league = League.objects.select_related("organization").get(
        steam_league_id=DTX_STEAM_LEAGUE_ID
    )
    existing = Tournament.objects.filter(name=CAPTAIN_REMOVAL_TOURNAMENT_NAME)
    if existing.exists():
        if not force:
            return existing.first()
        existing.delete()

    knocked_out = _roster("ko")
    winners = _roster("win")
    fresh_captain = _user("fresh")

    tournament = Tournament.objects.create(
        name=CAPTAIN_REMOVAL_TOURNAMENT_NAME,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )
    tournament.users.add(*knocked_out, *winners, fresh_captain)

    played = Team.objects.create(
        tournament=tournament,
        name=CAPTAIN_REMOVAL_PLAYED_TEAM,
        captain=knocked_out[0],
        deputy_captain=knocked_out[1],
        draft_order=1,
        placement=3,
    )
    played.members.set(knocked_out)

    winner_team = Team.objects.create(
        tournament=tournament, name="CR Winners", captain=winners[0], draft_order=2
    )
    winner_team.members.set(winners)

    fresh = Team.objects.create(
        tournament=tournament,
        name=CAPTAIN_REMOVAL_FRESH_TEAM,
        captain=fresh_captain,
        draft_order=3,
    )
    fresh.members.add(fresh_captain)

    Game.objects.create(
        tournament=tournament,
        radiant_team=played,
        dire_team=winner_team,
        winning_team=winner_team,
    )

    return Tournament.objects.get(pk=tournament.pk)
