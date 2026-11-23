from django.db.models import Sum

from app.models import CustomUser
from steam.functions.mmr_calculation import (
    calculate_mmr_adjustment,
    recompute_league_mmrs_for_users,
    update_user_league_mmr,
)
from steam.models import LeaguePlayerStats, PlayerMatchStats
from telemetry.logging import get_logger

logger = get_logger(__name__)


def player_won(player_slot: int, radiant_win: bool) -> bool:
    return (player_slot < 128) == radiant_win


def recompute_player_league_totals(
    user: CustomUser, league_id: int
) -> LeaguePlayerStats | None:
    """Save a player's league totals and averages; leaves mmr_adjustment alone."""
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

    totals = match_stats.aggregate(
        total_kills=Sum("kills"),
        total_deaths=Sum("deaths"),
        total_assists=Sum("assists"),
        total_gpm=Sum("gold_per_min"),
        total_xpm=Sum("xp_per_min"),
    )

    games_played = match_stats.count()

    wins = 0
    losses = 0
    for stat in match_stats:
        if player_won(stat.player_slot, stat.match.radiant_win):
            wins += 1
        else:
            losses += 1

    stats, _ = LeaguePlayerStats.objects.get_or_create(user=user, league_id=league_id)
    stats.games_played = games_played
    stats.wins = wins
    stats.losses = losses
    stats.total_kills = totals["total_kills"] or 0
    stats.total_deaths = totals["total_deaths"] or 0
    stats.total_assists = totals["total_assists"] or 0
    stats.total_gpm = totals["total_gpm"] or 0
    stats.total_xpm = totals["total_xpm"] or 0
    stats.recalculate_averages()
    stats.save()
    return stats


def apply_mmr_adjustment(stats: LeaguePlayerStats) -> None:
    stats.mmr_adjustment = calculate_mmr_adjustment(stats)
    stats.save(update_fields=["mmr_adjustment", "last_updated"])


def _log_stats_updated(user: CustomUser, stats: LeaguePlayerStats) -> None:
    logger.info(
        "league_stats_updated",
        system="steam",
        subsystem="stats",
        username=user.username,
        league_id=stats.league_id,
        games_played=stats.games_played,
        wins=stats.wins,
        losses=stats.losses,
        mmr_adjustment=stats.mmr_adjustment,
    )


def update_player_league_stats(
    user: CustomUser, league_id: int
) -> LeaguePlayerStats | None:
    """
    Recalculate a player's aggregated stats for a specific league.
    Creates LeaguePlayerStats if it doesn't exist.
    """
    stats = recompute_player_league_totals(user, league_id)
    if stats is None:
        return None

    apply_mmr_adjustment(stats)

    update_user_league_mmr(user)

    _log_stats_updated(user, stats)
    return stats


def league_user_ids(league_id: int) -> list[int]:
    return list(
        PlayerMatchStats.objects.filter(match__league_id=league_id, user__isnull=False)
        .values_list("user_id", flat=True)
        .distinct()
    )


def update_all_league_stats_for_league(league_id: int) -> int:
    """
    Update league stats for all users who have played in a league.
    Returns count of users updated.

    Every player's averages are saved before any adjustment is computed, so
    each adjustment sees the whole league's current averages.
    """
    user_ids = league_user_ids(league_id)
    users = CustomUser.objects.in_bulk(user_ids)

    updated: list[tuple[CustomUser, LeaguePlayerStats]] = []
    for user_id in user_ids:
        user = users.get(user_id)
        if user is None:
            continue
        stats = recompute_player_league_totals(user, league_id)
        if stats is not None:
            updated.append((user, stats))

    for _, stats in updated:
        apply_mmr_adjustment(stats)

    recompute_league_mmrs_for_users([user.pk for user, _ in updated])

    for user, stats in updated:
        _log_stats_updated(user, stats)

    logger.info(
        "league_stats_bulk_updated",
        system="steam",
        subsystem="stats",
        league_id=league_id,
        count=len(updated),
    )
    return len(updated)
