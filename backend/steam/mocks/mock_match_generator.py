"""
Mock Steam API match data generator.

Generates realistic match data using actual tournament team rosters,
ensuring player Steam IDs match the test users.
"""

import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Team, Tournament

# Hero IDs (popular competitive heroes)
HERO_IDS = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,  # Strength
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,  # Agility
    21,
    22,
    23,
    25,
    26,
    27,
    28,
    29,
    30,
    31,  # Intelligence
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    83,  # More heroes
    86,
    87,
    88,
    89,
    90,
    91,
    93,
    94,
    95,
    96,
]

# Stats ranges by position (pos 1-5)
POSITION_STATS = {
    0: {  # Carry (pos 1)
        "kills": (8, 18),
        "deaths": (1, 6),
        "assists": (5, 15),
        "gold_per_min": (500, 700),
        "xp_per_min": (600, 800),
        "last_hits": (250, 400),
        "denies": (5, 20),
        "hero_damage": (25000, 45000),
        "tower_damage": (3000, 10000),
        "hero_healing": (0, 500),
    },
    1: {  # Mid (pos 2)
        "kills": (6, 15),
        "deaths": (2, 7),
        "assists": (8, 18),
        "gold_per_min": (450, 650),
        "xp_per_min": (550, 750),
        "last_hits": (200, 350),
        "denies": (10, 30),
        "hero_damage": (20000, 40000),
        "tower_damage": (2000, 8000),
        "hero_healing": (0, 1000),
    },
    2: {  # Offlane (pos 3)
        "kills": (3, 10),
        "deaths": (3, 8),
        "assists": (10, 22),
        "gold_per_min": (350, 500),
        "xp_per_min": (450, 600),
        "last_hits": (100, 200),
        "denies": (3, 15),
        "hero_damage": (15000, 30000),
        "tower_damage": (1000, 5000),
        "hero_healing": (0, 2000),
    },
    3: {  # Soft Support (pos 4)
        "kills": (2, 8),
        "deaths": (4, 10),
        "assists": (15, 28),
        "gold_per_min": (250, 400),
        "xp_per_min": (350, 500),
        "last_hits": (30, 80),
        "denies": (1, 10),
        "hero_damage": (8000, 20000),
        "tower_damage": (500, 3000),
        "hero_healing": (0, 8000),
    },
    4: {  # Hard Support (pos 5)
        "kills": (1, 5),
        "deaths": (5, 12),
        "assists": (18, 32),
        "gold_per_min": (200, 350),
        "xp_per_min": (300, 450),
        "last_hits": (20, 50),
        "denies": (0, 8),
        "hero_damage": (5000, 15000),
        "tower_damage": (200, 2000),
        "hero_healing": (0, 15000),
    },
}


def generate_player_stats(
    user, position: int, is_winner: bool, player_slot: int
) -> dict:
    """
    Generate realistic player stats based on position and win/loss.

    Args:
        user: CustomUser instance with steamid
        position: 0-4 representing pos 1-5
        is_winner: Whether player's team won
        player_slot: 0-4 for Radiant, 128-132 for Dire

    Returns:
        Dict matching Steam API player response format
    """
    stats = POSITION_STATS.get(position, POSITION_STATS[4])

    # Winners get slightly better stats on average
    multiplier = 1.1 if is_winner else 0.9

    def rand_stat(key):
        low, high = stats[key]
        base = random.randint(low, high)
        # Apply multiplier with some variance
        return int(base * multiplier * random.uniform(0.9, 1.1))

    # Convert 64-bit Steam ID to 32-bit account_id
    account_id = user.steamid - 76561197960265728

    return {
        "account_id": account_id,
        "player_slot": player_slot,
        "hero_id": random.choice(HERO_IDS),
        "kills": rand_stat("kills"),
        "deaths": rand_stat("deaths"),
        "assists": rand_stat("assists"),
        "gold_per_min": rand_stat("gold_per_min"),
        "xp_per_min": rand_stat("xp_per_min"),
        "last_hits": rand_stat("last_hits"),
        "denies": rand_stat("denies"),
        "hero_damage": rand_stat("hero_damage"),
        "tower_damage": rand_stat("tower_damage"),
        "hero_healing": rand_stat("hero_healing"),
    }


def generate_mock_match(
    radiant_team: "Team",
    dire_team: "Team",
    match_id: int,
    start_time: int,
    radiant_win: bool = None,
) -> dict:
    """
    Generate a mock Steam API match response.

    Args:
        radiant_team: Team model instance for Radiant side
        dire_team: Team model instance for Dire side
        match_id: Unique match ID
        start_time: Unix timestamp for match start
        radiant_win: If None, randomly determined

    Returns:
        Dict matching Steam API GetMatchDetails response format
    """
    if radiant_win is None:
        radiant_win = random.choice([True, False])

    # Duration: 25-55 minutes
    duration = random.randint(1500, 3300)

    players = []

    # Radiant players (slots 0-4)
    radiant_members = list(radiant_team.members.all())[:5]
    for i, user in enumerate(radiant_members):
        players.append(
            generate_player_stats(
                user=user,
                position=i,
                is_winner=radiant_win,
                player_slot=i,
            )
        )

    # Dire players (slots 128-132)
    dire_members = list(dire_team.members.all())[:5]
    for i, user in enumerate(dire_members):
        players.append(
            generate_player_stats(
                user=user,
                position=i,
                is_winner=not radiant_win,
                player_slot=128 + i,
            )
        )

    return {
        "result": {
            "match_id": match_id,
            "radiant_win": radiant_win,
            "duration": duration,
            "start_time": start_time,
            "game_mode": 2,  # Captain's Mode
            "lobby_type": 1,  # Practice
            "players": players,
        }
    }


def generate_double_elim_bracket_matches(
    teams: list["Team"],
    base_match_id: int = 9000000001,
    base_time: int = None,
) -> list[dict]:
    """
    Generate mock matches for a 4-team double elimination bracket.

    Bracket structure:
    - Winners R1: Match 1 (Team1 vs Team2), Match 2 (Team3 vs Team4)
    - Losers R1: Match 3 (Loser1 vs Loser2)
    - Winners Final: Match 4 (Winner1 vs Winner2)
    - Losers Final: Match 5 (Winner3 vs Loser4)
    - Grand Final: Match 6 (WinnersFinal vs LosersFinal)
    - Grand Final Reset: Match 7 (if losers bracket winner wins Match 6)

    Args:
        teams: List of 4 Team instances
        base_match_id: Starting match ID
        base_time: Starting timestamp (defaults to now)

    Returns:
        List of mock match dicts in bracket order
    """
    if len(teams) < 4:
        raise ValueError("Need at least 4 teams for double elimination")

    if base_time is None:
        base_time = int(datetime.now().timestamp())

    matches = []
    match_id = base_match_id
    current_time = base_time

    # Time between matches (1 hour)
    match_interval = 3600

    # Winners Round 1
    # Match 1: Team 0 vs Team 1
    match1 = generate_mock_match(
        radiant_team=teams[0],
        dire_team=teams[1],
        match_id=match_id,
        start_time=current_time,
    )
    matches.append(match1)
    w1_winner = teams[0] if match1["result"]["radiant_win"] else teams[1]
    w1_loser = teams[1] if match1["result"]["radiant_win"] else teams[0]
    match_id += 1
    current_time += match_interval

    # Match 2: Team 2 vs Team 3
    match2 = generate_mock_match(
        radiant_team=teams[2],
        dire_team=teams[3],
        match_id=match_id,
        start_time=current_time,
    )
    matches.append(match2)
    w2_winner = teams[2] if match2["result"]["radiant_win"] else teams[3]
    w2_loser = teams[3] if match2["result"]["radiant_win"] else teams[2]
    match_id += 1
    current_time += match_interval

    # Losers Round 1: Loser1 vs Loser2
    match3 = generate_mock_match(
        radiant_team=w1_loser,
        dire_team=w2_loser,
        match_id=match_id,
        start_time=current_time,
    )
    matches.append(match3)
    l1_winner = w1_loser if match3["result"]["radiant_win"] else w2_loser
    match_id += 1
    current_time += match_interval

    # Winners Final: Winner1 vs Winner2
    match4 = generate_mock_match(
        radiant_team=w1_winner,
        dire_team=w2_winner,
        match_id=match_id,
        start_time=current_time,
    )
    matches.append(match4)
    wf_winner = w1_winner if match4["result"]["radiant_win"] else w2_winner
    wf_loser = w2_winner if match4["result"]["radiant_win"] else w1_winner
    match_id += 1
    current_time += match_interval

    # Losers Final: L1 Winner vs WF Loser
    match5 = generate_mock_match(
        radiant_team=l1_winner,
        dire_team=wf_loser,
        match_id=match_id,
        start_time=current_time,
    )
    matches.append(match5)
    lf_winner = l1_winner if match5["result"]["radiant_win"] else wf_loser
    match_id += 1
    current_time += match_interval

    # Grand Final: Winners Final Winner vs Losers Final Winner
    match6 = generate_mock_match(
        radiant_team=wf_winner,
        dire_team=lf_winner,
        match_id=match_id,
        start_time=current_time,
    )
    matches.append(match6)

    # Grand Final Reset (if losers bracket winner wins)
    if not match6["result"]["radiant_win"]:
        match_id += 1
        current_time += match_interval
        match7 = generate_mock_match(
            radiant_team=wf_winner,
            dire_team=lf_winner,
            match_id=match_id,
            start_time=current_time,
        )
        matches.append(match7)

    return matches


def generate_mock_matches_for_tournament(tournament: "Tournament") -> list[dict]:
    """
    Generate mock Steam matches for a tournament's bracket.

    Args:
        tournament: Tournament instance with teams

    Returns:
        List of mock match dicts ready to be saved
    """
    teams = list(tournament.teams.all()[:4])

    if len(teams) < 4:
        raise ValueError(f"Tournament needs at least 4 teams, has {len(teams)}")

    # Use tournament date as base time
    if tournament.date_played:
        base_time = int(tournament.date_played.timestamp())
    else:
        base_time = int(datetime.now().timestamp())

    return generate_double_elim_bracket_matches(
        teams=teams,
        base_match_id=9000000001,
        base_time=base_time,
    )
