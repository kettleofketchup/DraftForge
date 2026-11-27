from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Avg

from league.mmr_sync import recompute_league_mmrs
from org.mmr import LEAGUE_GAME
from org.models import OrgUserGameMmr
from steam.models import LeaguePlayerStats

if TYPE_CHECKING:
    from app.models import CustomUser
    from league.models import League
    from org.models import Organization


def get_league_avg_kda(league_id: int) -> float:
    """Get the average KDA for all players in a league."""
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
    result = LeaguePlayerStats.objects.filter(
        league_id=league_id,
        games_played__gte=settings.LEAGUE_MMR_MIN_GAMES,
    ).aggregate(avg_gpm=Avg("avg_gpm"))

    return result["avg_gpm"] or 400  # Default to 400 GPM


def calculate_mmr_adjustment(stats: LeaguePlayerStats) -> int:
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


def recompute_league_mmrs_for_users(
    user_ids: Iterable[int],
    *,
    organization_id: int | None = None,
    league_id: int | None = None,
) -> list[int]:
    """Recompute unverified league MMRs (org MMR + best adjustment) for users."""
    ids = list(user_ids)
    if not ids:
        return []
    rows = OrgUserGameMmr.objects.nocache().filter(
        org_user__user_id__in=ids, game_type=LEAGUE_GAME
    )
    if organization_id is not None:
        rows = rows.filter(org_user__organization_id=organization_id)
    base_mmrs = dict(rows.values_list("org_user_id", "mmr"))
    return recompute_league_mmrs(base_mmrs, trigger="adjustment", league_id=league_id)


def update_user_league_mmr(
    user: CustomUser,
    organization: Organization | None = None,
    league: League | None = None,
) -> list[int]:
    """Recompute the user's league MMRs, optionally scoped to an org or league."""
    return recompute_league_mmrs_for_users(
        [user.pk],
        organization_id=organization.pk if organization is not None else None,
        league_id=league.pk if league is not None else None,
    )
