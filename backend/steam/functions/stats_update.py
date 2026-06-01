from django.db.models import Sum

from steam.functions.mmr_calculation import (
    calculate_mmr_adjustment,
    update_user_league_mmr,
)
from steam.models import LeaguePlayerStats, PlayerMatchStats
from telemetry.logging import get_logger

logger = get_logger(__name__)


def update_player_league_stats(user, league_id: int) -> LeaguePlayerStats:
    """
    Recalculate a player's aggregated stats for a specific league.
    Creates LeaguePlayerStats if it doesn't exist.
    """
    # Get all player's match stats for this league
    match_stats = PlayerMatchStats.objects.filter(
        user=user,
        match__league_id=league_id,
    ).select_related("match")

    if not match_stats.exists():
        logger.debug(
            "stats_not_found",
            system="steam",
            subsystem="stats",
            username=user.username,
            league_id=league_id,
        )
        return None

    # Calculate aggregates
    totals = match_stats.aggregate(
        total_kills=Sum("kills"),
        total_deaths=Sum("deaths"),
        total_assists=Sum("assists"),
        total_gpm=Sum("gold_per_min"),
        total_xpm=Sum("xp_per_min"),
    )

    games_played = match_stats.count()

    # Calculate wins/losses
    wins = 0
    losses = 0
    for stat in match_stats:
        is_radiant = stat.player_slot < 128
        player_won = (is_radiant and stat.match.radiant_win) or (
            not is_radiant and not stat.match.radiant_win
        )
        if player_won:
            wins += 1
        else:
            losses += 1

    # Create or update LeaguePlayerStats
    stats, created = LeaguePlayerStats.objects.update_or_create(
        user=user,
        league_id=league_id,
        defaults={
            "games_played": games_played,
            "wins": wins,
            "losses": losses,
            "total_kills": totals["total_kills"] or 0,
            "total_deaths": totals["total_deaths"] or 0,
            "total_assists": totals["total_assists"] or 0,
            "total_gpm": totals["total_gpm"] or 0,
            "total_xpm": totals["total_xpm"] or 0,
        },
    )

    # Recalculate averages
    stats.recalculate_averages()

    # Calculate MMR adjustment
    stats.mmr_adjustment = calculate_mmr_adjustment(stats)
    stats.save()

    # Update user's league_mmr
    update_user_league_mmr(user)

    logger.info(
        "league_stats_updated",
        system="steam",
        subsystem="stats",
        username=user.username,
        league_id=league_id,
        games_played=games_played,
        wins=wins,
        losses=losses,
        mmr_adjustment=stats.mmr_adjustment,
    )

    return stats


def update_all_league_stats_for_league(league_id: int) -> int:
    """
    Update league stats for all users who have played in a league.
    Returns count of users updated.
    """
    from app.models import CustomUser

    # Find all users with match stats in this league
    user_ids = (
        PlayerMatchStats.objects.filter(match__league_id=league_id, user__isnull=False)
        .values_list("user_id", flat=True)
        .distinct()
    )

    updated_count = 0
    for user_id in user_ids:
        try:
            user = CustomUser.objects.get(pk=user_id)
            update_player_league_stats(user, league_id)
            updated_count += 1
        except CustomUser.DoesNotExist:
            continue

    logger.info(
        "league_stats_bulk_updated",
        system="steam",
        subsystem="stats",
        league_id=league_id,
        count=updated_count,
    )
    return updated_count
