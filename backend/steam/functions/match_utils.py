import logging

from django.db.models import Count, Q

from steam.models import Match, PlayerMatchStats

log = logging.getLogger(__name__)


def find_matches_by_players(steam_ids, require_all=True, league_id=None):
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
