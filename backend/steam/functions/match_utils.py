from collections.abc import Iterable
from typing import Any

from django.db.models import QuerySet

from app.models import Team
from steam.models import Match
from steam.utils.steam_api_caller import SteamAPI
from telemetry.logging import get_logger

log = get_logger(__name__)


def find_matches_by_players(
    steam_ids: Iterable[int], require_all: bool = True, league_id: int | None = None
) -> QuerySet[Match]:
    """
    Find historical matches where given players participated.

    Args:
        steam_ids: List of Steam IDs to search for
        require_all: If True, all players must be in match. If False, any player.
        league_id: Optional filter to specific league

    Returns:
        QuerySet of Match objects
    """
    if not steam_ids:
        return Match.objects.none()

    queryset = Match.objects.all()

    if league_id:
        queryset = queryset.filter(league_id=league_id)

    if require_all:
        # Match must contain ALL specified players
        for steam_id in steam_ids:
            queryset = queryset.filter(players__steam_id=steam_id)
        queryset = queryset.distinct()
    else:
        # Match must contain ANY of the specified players
        queryset = queryset.filter(players__steam_id__in=steam_ids).distinct()

    return queryset.prefetch_related("players")


def find_matches_by_team(team_id: int) -> QuerySet[Match]:
    """
    Find all matches where members of a Team played together.
    Looks up team members' steamids and calls find_matches_by_players.

    Returns: QuerySet of Match objects
    """
    try:
        team = Team.objects.get(id=team_id)
    except Team.DoesNotExist:
        return Match.objects.none()

    # Get steamids from team members (team.members is M2M to CustomUser)
    # steamid is an IntegerField, so we only need to exclude null values
    steam_ids = list(
        team.members.exclude(steamid__isnull=True).values_list("steamid", flat=True)
    )

    if not steam_ids:
        return Match.objects.none()

    # Use require_all=False to find any match with team members
    return find_matches_by_players(steam_ids, require_all=False)


def find_live_game_by_players(
    steam_ids: Iterable[int | str], league_id: int | None = None
) -> dict[str, Any] | None:
    """
    Check if any of the given players are in a live game.
    Calls Steam API GetLiveLeagueGames and filters by player list.

    Returns: Live game data dict or None
    """
    if not steam_ids:
        return None

    steam_ids_set = set(int(sid) for sid in steam_ids)

    api = SteamAPI()
    response = api.get_live_league_games(league_id=league_id)

    if not response or "result" not in response:
        return None

    games = response["result"].get("games", [])

    for game in games:
        # Check players in both radiant and dire
        players = game.get("players", [])
        for player in players:
            account_id = player.get("account_id")
            if account_id:
                # Convert 32-bit account_id to 64-bit steam_id
                steam_id_64 = account_id + 76561197960265728
                if steam_id_64 in steam_ids_set:
                    return game

    return None
