"""Discord Activity bracket fixture: "Activity Bracket Test" with bracket games."""

from app.models import CustomUser
from tests.data.tournaments import ACTIVITY_BRACKET_CONFIG
from tests.populate.steam import populate_bracket_games_for_tournament
from tests.populate.tournaments import create_dynamic_tournament
from tournament.models import Game

from .constants import DTX_STEAM_LEAGUE_ID
from .utils import flush_redis_cache

DOUBLE_ELIM_4_TEAMS: list[dict[str, object]] = [
    {"round": 1, "bracket_type": "winners", "position": 0},
    {"round": 1, "bracket_type": "winners", "position": 1},
    {"round": 1, "bracket_type": "losers", "position": 0},
    {"round": 2, "bracket_type": "winners", "position": 0},
    {"round": 2, "bracket_type": "losers", "position": 0},
    {"round": 1, "bracket_type": "grand_finals", "position": 0},
]


def populate_activity_bracket_data(force: bool = False) -> None:
    users = CustomUser.objects.filter(
        org_memberships__organization_id=ACTIVITY_BRACKET_CONFIG.organization_pk
    )
    tournament = create_dynamic_tournament(
        ACTIVITY_BRACKET_CONFIG, force=force, users=users
    )
    if tournament is None:
        return
    games = Game.objects.filter(tournament=tournament)
    if games.exists():
        if not force:
            print(f"'{tournament.name}' already has bracket games, skipping...")
            return
        games.delete()
    populate_bracket_games_for_tournament(
        tournament,
        ACTIVITY_BRACKET_CONFIG,
        DOUBLE_ELIM_4_TEAMS,
        steam_league_id=DTX_STEAM_LEAGUE_ID,
    )
    flush_redis_cache()
