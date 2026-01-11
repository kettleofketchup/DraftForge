"""
Steam match generation helpers for testing.

Provides functions to generate mock Steam matches with player statistics,
ensuring unique match IDs across test runs.
"""

import random
from datetime import datetime, timedelta
from typing import Optional, Set

from app.models import CustomUser, Team
from steam.models import Match, PlayerMatchStats

# Track used match IDs to ensure uniqueness within a test run
_used_match_ids: Set[int] = set()

# Default prefix for test match IDs (avoids collision with real Steam IDs)
TEST_MATCH_ID_PREFIX = 9000000000


def generate_unique_match_id(prefix: int = TEST_MATCH_ID_PREFIX) -> int:
    """
    Generate a unique match ID for testing.

    Uses a prefix in the 9 billion range to avoid collisions with real
    Steam match IDs. Tracks used IDs to ensure uniqueness within a test run.

    Args:
        prefix: Base prefix for match IDs (default: 9000000000)

    Returns:
        Unique match ID
    """
    while True:
        match_id = prefix + random.randint(1, 99999999)
        if match_id not in _used_match_ids:
            _used_match_ids.add(match_id)
            return match_id


def reset_match_id_tracker() -> None:
    """
    Reset the match ID tracker.

    Call this at the start of a test suite to allow ID reuse between runs.
    """
    global _used_match_ids
    _used_match_ids.clear()


def generate_steam_match(
    radiant_team: Team,
    dire_team: Team,
    radiant_win: Optional[bool] = None,
    duration: Optional[int] = None,
    match_id: Optional[int] = None,
) -> Match:
    """
    Generate a mock Steam match with player stats.

    Creates a Match instance with PlayerMatchStats for all members of both teams.
    Stats are randomly generated with winners generally having better numbers.

    Args:
        radiant_team: Team playing radiant side
        dire_team: Team playing dire side
        radiant_win: Force winner (random if None)
        duration: Match duration in seconds (random 20-60 min if None)
        match_id: Specific match ID (generated if None)

    Returns:
        Created Match instance with associated PlayerMatchStats

    Example:
        >>> match = generate_steam_match(team_alpha, team_beta)
        >>> match = generate_steam_match(team_alpha, team_beta, radiant_win=True)
        >>> match = generate_steam_match(team_alpha, team_beta, duration=2400)
    """
    if radiant_win is None:
        radiant_win = random.choice([True, False])

    if duration is None:
        duration = random.randint(1200, 3600)  # 20-60 minutes

    if match_id is None:
        match_id = generate_unique_match_id()

    match = Match.objects.create(
        match_id=match_id,
        radiant_win=radiant_win,
        duration=duration,
        start_time=int(
            (datetime.now() - timedelta(hours=random.randint(1, 48))).timestamp()
        ),
        game_mode=22,  # All Pick
        lobby_type=1,  # Practice
        league_id=17929,
    )

    # Generate player stats for both teams
    _generate_team_stats(match, radiant_team, is_radiant=True, won=radiant_win)
    _generate_team_stats(match, dire_team, is_radiant=False, won=not radiant_win)

    return match


def _generate_team_stats(match: Match, team: Team, is_radiant: bool, won: bool) -> None:
    """
    Generate player stats for a team in a match.

    Args:
        match: The Match instance to attach stats to
        team: Team to generate stats for
        is_radiant: Whether team is on radiant side
        won: Whether the team won
    """
    members = list(team.members.all())[:5]

    for idx, player in enumerate(members):
        # Player slot: 0-4 for radiant, 128-132 for dire
        slot = idx if is_radiant else idx + 128

        # Winners generally have better stats
        kill_base = 8 if won else 5
        death_base = 5 if won else 8

        # Generate Steam ID - use player's steamid or generate from pk
        steam_id = player.steamid or (76561197960265728 + player.pk)

        PlayerMatchStats.objects.update_or_create(
            match=match,
            steam_id=steam_id,
            defaults={
                "user": player,
                "player_slot": slot,
                "hero_id": random.randint(1, 130),
                "kills": random.randint(max(0, kill_base - 3), kill_base + 7),
                "deaths": random.randint(max(0, death_base - 3), death_base + 5),
                "assists": random.randint(5, 20),
                "gold_per_min": random.randint(350, 700),
                "xp_per_min": random.randint(400, 800),
                "last_hits": random.randint(50, 300),
                "denies": random.randint(0, 30),
                "hero_damage": random.randint(10000, 40000),
                "tower_damage": random.randint(0, 8000),
                "hero_healing": random.randint(0, 5000),
            },
        )


def generate_match_for_game(
    game,
    radiant_win: Optional[bool] = None,
) -> Match:
    """
    Generate a Steam match for an existing Game object.

    Convenience function that extracts teams from a Game and generates
    a match, then updates the Game with the match ID.

    Args:
        game: Game instance with radiant_team and dire_team set
        radiant_win: Force winner (random if None)

    Returns:
        Created Match instance
    """
    if not game.radiant_team or not game.dire_team:
        raise ValueError("Game must have both radiant_team and dire_team set")

    match = generate_steam_match(
        radiant_team=game.radiant_team,
        dire_team=game.dire_team,
        radiant_win=radiant_win,
    )

    # Update game with match info
    game.gameid = match.match_id
    game.status = "completed"
    game.winning_team = game.radiant_team if match.radiant_win else game.dire_team
    game.save()

    return match
