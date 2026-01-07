import logging

from django.conf import settings
from django.db.models import Avg, Max

logger = logging.getLogger(__name__)


def get_league_avg_kda(league_id: int) -> float:
    """Get the average KDA for all players in a league."""
    from steam.models import LeaguePlayerStats

    stats = LeaguePlayerStats.objects.filter(
        league_id=league_id,
        games_played__gte=settings.LEAGUE_MMR_MIN_GAMES,
    ).aggregate(
        avg_kills=Avg("avg_kills"),
        avg_deaths=Avg("avg_deaths"),
        avg_assists=Avg("avg_assists"),
    )

    avg_kills = stats["avg_kills"] or 0
    avg_deaths = stats["avg_deaths"] or 1
    avg_assists = stats["avg_assists"] or 0

    return (avg_kills + avg_assists) / max(avg_deaths, 1)


def get_league_avg_gpm(league_id: int) -> float:
    """Get the average GPM for all players in a league."""
    from steam.models import LeaguePlayerStats

    result = LeaguePlayerStats.objects.filter(
        league_id=league_id,
        games_played__gte=settings.LEAGUE_MMR_MIN_GAMES,
    ).aggregate(avg_gpm=Avg("avg_gpm"))

    return result["avg_gpm"] or 400  # Default to 400 GPM


def calculate_mmr_adjustment(stats) -> int:
    """
    Calculate MMR adjustment based on league performance.
    Returns 0 if below minimum games threshold.
    Range: -500 to +500
    """
    min_games = getattr(settings, "LEAGUE_MMR_MIN_GAMES", 5)

    if stats.games_played < min_games:
        return 0

    # Factor 1: Win rate (50% = neutral)
    # 60% = +20, 40% = -20
    win_factor = (stats.win_rate - 0.5) * 200

    # Factor 2: KDA vs league average
    player_kda = (stats.avg_kills + stats.avg_assists) / max(stats.avg_deaths, 1)
    league_avg_kda = get_league_avg_kda(stats.league_id)
    kda_diff = player_kda - league_avg_kda
    kda_factor = kda_diff * 50  # ~50 per point above/below avg

    # Factor 3: GPM vs league average
    league_avg_gpm = get_league_avg_gpm(stats.league_id)
    gpm_diff = stats.avg_gpm - league_avg_gpm
    gpm_factor = gpm_diff * 0.5  # ~50 per 100 GPM difference

    # Combine and clamp
    adjustment = int(win_factor + kda_factor + gpm_factor)
    return max(-500, min(500, adjustment))


def update_user_league_mmr(user) -> None:
    """
    Set user's league_mmr to base mmr + best league adjustment.
    """
    if not user.mmr:
        user.league_mmr = None
        user.save(update_fields=["league_mmr"])
        return

    best_adjustment = user.league_stats.aggregate(Max("mmr_adjustment"))[
        "mmr_adjustment__max"
    ]

    if best_adjustment is None:
        best_adjustment = 0

    user.league_mmr = user.mmr + best_adjustment
    user.save(update_fields=["league_mmr"])
    logger.debug(
        f"Updated {user.username} league_mmr to {user.league_mmr} "
        f"(base: {user.mmr}, adjustment: {best_adjustment})"
    )
