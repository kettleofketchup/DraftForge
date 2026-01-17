from django.db.models import Q

from app.models import Game, Team
from steam.models import Match, PlayerMatchStats, SuggestionTier


def get_team_steam_ids(team: Team) -> set[int]:
    """Get all steam IDs for a team's members."""
    return set(
        team.members.exclude(steamid__isnull=True)
        .exclude(steamid=0)
        .values_list("steamid", flat=True)
    )


def calculate_suggestion_tier(
    match: Match,
    all_team_steam_ids: set[int],
    radiant_captain_id: int | None,
    dire_captain_id: int | None,
) -> SuggestionTier:
    """
    Calculate the suggestion tier based on player overlap.

    Tiers:
    - ALL_PLAYERS: All 10 players match
    - CAPTAINS_PLUS: Both captains + some other players match
    - CAPTAINS_ONLY: Only both captains match
    - PARTIAL: Some players match but not both captains
    """
    match_steam_ids = set(
        PlayerMatchStats.objects.filter(match=match).values_list("steam_id", flat=True)
    )

    overlap = all_team_steam_ids & match_steam_ids

    both_captains_present = (
        radiant_captain_id in match_steam_ids and dire_captain_id in match_steam_ids
    )

    if len(overlap) >= 10:
        return SuggestionTier.ALL_PLAYERS
    elif both_captains_present and len(overlap) > 2:
        return SuggestionTier.CAPTAINS_PLUS
    elif both_captains_present:
        return SuggestionTier.CAPTAINS_ONLY
    else:
        return SuggestionTier.PARTIAL


def get_match_suggestions_for_game(game: Game, search: str | None = None) -> list[dict]:
    """
    Get match suggestions for a bracket game with tiered ordering.

    Returns matches from the tournament's league that aren't already linked,
    ordered by tier (best matches first).
    """
    if not game.radiant_team or not game.dire_team:
        return []

    tournament = game.tournament
    league_id = tournament.steam_league_id

    if not league_id:
        return []

    # Get matches from this league that aren't linked to any game
    linked_match_ids = Game.objects.filter(gameid__isnull=False).values_list(
        "gameid", flat=True
    )

    matches_query = Match.objects.filter(league_id=league_id).exclude(
        match_id__in=linked_match_ids
    )

    # Apply search filter
    if search:
        # Try to parse as match ID
        try:
            match_id = int(search)
            matches_query = matches_query.filter(match_id__icontains=str(match_id))
        except ValueError:
            # Search by captain name - get captain steam IDs matching the search
            from app.models import CustomUser

            matching_users = (
                CustomUser.objects.filter(
                    Q(username__icontains=search)
                    | Q(nickname__icontains=search)
                    | Q(discordUsername__icontains=search)
                    | Q(discordNickname__icontains=search)
                    | Q(guildNickname__icontains=search)
                )
                .exclude(steamid__isnull=True)
                .exclude(steamid=0)
            )

            matching_steam_ids = list(matching_users.values_list("steamid", flat=True))

            if matching_steam_ids:
                # Find matches containing these players
                match_ids_with_player = PlayerMatchStats.objects.filter(
                    steam_id__in=matching_steam_ids
                ).values_list("match_id", flat=True)
                matches_query = matches_query.filter(match_id__in=match_ids_with_player)
            else:
                return []

    matches = list(matches_query.prefetch_related("players__user")[:50])

    # Pre-compute team steam IDs and captain IDs (avoids N+1 queries in the loop)
    radiant_steam_ids = get_team_steam_ids(game.radiant_team)
    dire_steam_ids = get_team_steam_ids(game.dire_team)
    all_team_steam_ids = radiant_steam_ids | dire_steam_ids

    radiant_captain = game.radiant_team.captain
    dire_captain = game.dire_team.captain
    radiant_captain_id = (
        radiant_captain.steamid if radiant_captain and radiant_captain.steamid else None
    )
    dire_captain_id = (
        dire_captain.steamid if dire_captain and dire_captain.steamid else None
    )

    # Calculate tier for each match and build response
    suggestions = []
    for match in matches:
        tier = calculate_suggestion_tier(
            match, all_team_steam_ids, radiant_captain_id, dire_captain_id
        )

        # Get captain info from match
        radiant_captain_info = _get_captain_match_info(match, radiant_captain)
        dire_captain_info = _get_captain_match_info(match, dire_captain)

        suggestions.append(
            {
                "match_id": match.match_id,
                "start_time": match.start_time,
                "duration": match.duration,
                "radiant_win": match.radiant_win,
                "tier": tier,
                "tier_display": tier.label,
                "player_overlap": _count_player_overlap(match, all_team_steam_ids),
                "radiant_captain": radiant_captain_info,
                "dire_captain": dire_captain_info,
            }
        )

    # Sort by tier priority
    tier_order = {
        SuggestionTier.ALL_PLAYERS: 0,
        SuggestionTier.CAPTAINS_PLUS: 1,
        SuggestionTier.CAPTAINS_ONLY: 2,
        SuggestionTier.PARTIAL: 3,
    }
    suggestions.sort(key=lambda s: (tier_order[s["tier"]], -s["start_time"]))

    return suggestions


def _get_captain_match_info(match: Match, captain) -> dict | None:
    """Get captain's info from match stats if they played."""
    if not captain or not captain.steamid:
        return None

    try:
        stats = PlayerMatchStats.objects.get(match=match, steam_id=captain.steamid)
        return {
            "steam_id": captain.steamid,
            "username": captain.username,
            "avatar": captain.avatarUrl if hasattr(captain, "avatarUrl") else None,
            "hero_id": stats.hero_id,
        }
    except PlayerMatchStats.DoesNotExist:
        return None


def _count_player_overlap(match: Match, all_team_steam_ids: set[int]) -> int:
    """Count how many team players are in the match."""
    match_steam_ids = set(
        PlayerMatchStats.objects.filter(match=match).values_list("steam_id", flat=True)
    )
    return len(all_team_steam_ids & match_steam_ids)
