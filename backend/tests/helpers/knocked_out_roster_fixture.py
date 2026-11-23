"""Playwright fixture for issue #842: removing a player keeps knocked-out rosters.

Not covered by the test-db hash: the tournament is built on demand through
``/api/tests/reset-tournament/knocked_out_roster/``.
"""

from datetime import date

from app.models import CustomUser
from league.models import League
from tests.populate.constants import DTX_STEAM_LEAGUE_ID
from tournament.models import Team, Tournament

KNOCKED_OUT_ROSTER_TOURNAMENT_NAME: str = "Knocked Out Roster Tournament"
KNOCKED_OUT_ROSTER_USER_PREFIX: str = "ko_roster_"


def _roster(key: str) -> list[CustomUser]:
    return [
        CustomUser.objects.get_or_create(
            username=f"{KNOCKED_OUT_ROSTER_USER_PREFIX}{key}_{n}"
        )[0]
        for n in range(1, 6)
    ]


def populate_knocked_out_roster_tournament(force: bool = False) -> Tournament:
    """KO Out is knocked out (placement 3); KO Live is still playing."""
    league = League.objects.select_related("organization").get(
        steam_league_id=DTX_STEAM_LEAGUE_ID
    )
    existing = Tournament.objects.filter(name=KNOCKED_OUT_ROSTER_TOURNAMENT_NAME)
    if existing.exists():
        if not force:
            return existing.first()
        existing.delete()

    out = _roster("out")
    live = _roster("live")
    tournament = Tournament.objects.create(
        name=KNOCKED_OUT_ROSTER_TOURNAMENT_NAME,
        date_played=date.today(),
        state="in_progress",
        tournament_type="double_elimination",
        league=league,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )
    tournament.users.add(*out, *live)

    out_team = Team.objects.create(
        tournament=tournament,
        name="KO Out",
        captain=out[0],
        deputy_captain=out[1],
        draft_order=1,
        placement=3,
    )
    out_team.members.set(out)

    live_team = Team.objects.create(
        tournament=tournament, name="KO Live", captain=live[0], draft_order=2
    )
    live_team.members.set(live)

    return Tournament.objects.get(pk=tournament.pk)
