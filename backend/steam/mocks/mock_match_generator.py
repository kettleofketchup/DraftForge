"""
Mock Steam API match data generator.

Generates realistic match data matching the official Steam Web API structure
from GetMatchHistoryBySequenceNum endpoint. Uses actual tournament team rosters,
ensuring player Steam IDs match the test users.

Reference: https://api.steampowered.com/IDOTA2Match_570/GetMatchHistoryBySequenceNum/v1/
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
    35,
    37,
    39,
    41,
    43,
    44,
    45,
    46,
    47,
    48,  # More heroes
    49,
    50,
    51,
    55,
    60,
    64,
    67,
    70,
    72,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    83,
    84,
    85,
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
    97,
    98,
    99,
    102,
    104,
    106,
    110,
    114,
    123,
    128,
    135,
    136,
]

# Common item IDs for mock data
ITEM_IDS = [
    1,
    11,
    16,
    20,
    34,
    36,
    41,
    43,
    48,
    50,  # Basic items
    63,
    65,
    73,
    100,
    102,
    108,
    110,
    114,
    116,
    125,  # Mid-tier
    127,
    135,
    147,
    149,
    158,
    168,
    176,
    188,
    204,
    206,  # Late-game
    218,
    225,
    247,
    254,
    263,
    534,
    604,
    610,
    1097,
    1107,  # Advanced
]

# Neutral items by tier
NEUTRAL_ITEMS = [359, 1158, 1168, 1577, 1583, 1586, 1589, 1604, 1643, 1721]

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
    user, position: int, is_winner: bool, player_slot: int, duration: int
) -> dict:
    """
    Generate realistic player stats based on position and win/loss.

    Matches the official Steam Web API GetMatchHistoryBySequenceNum player format.

    Args:
        user: CustomUser instance with steamid
        position: 0-4 representing pos 1-5
        is_winner: Whether player's team won
        player_slot: 0-4 for Radiant, 128-132 for Dire
        duration: Match duration in seconds (affects gold/xp totals)

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

    # Team number: 0 for Radiant, 1 for Dire
    team_number = 0 if player_slot < 128 else 1
    team_slot = player_slot if team_number == 0 else player_slot - 128

    # Generate core stats
    kills = rand_stat("kills")
    deaths = rand_stat("deaths")
    assists = rand_stat("assists")
    gpm = rand_stat("gold_per_min")
    xpm = rand_stat("xp_per_min")
    last_hits = rand_stat("last_hits")
    denies = rand_stat("denies")
    hero_damage = rand_stat("hero_damage")
    tower_damage = rand_stat("tower_damage")
    hero_healing = rand_stat("hero_healing")

    # Calculate derived stats based on GPM/XPM and duration
    minutes = duration / 60
    net_worth = int(gpm * minutes * random.uniform(0.9, 1.1))
    gold = random.randint(500, 5000)  # Gold on hand
    gold_spent = net_worth - gold

    # Level based on XPM (max 30)
    level = min(30, max(15, int(xpm * minutes / 1500)))

    # Generate items (6 inventory slots)
    items = random.sample(ITEM_IDS, min(6, len(ITEM_IDS)))
    while len(items) < 6:
        items.append(0)

    # Aghanim's based on position/role
    has_scepter = random.random() < (0.6 if position <= 2 else 0.3)
    has_shard = random.random() < (0.7 if position <= 2 else 0.5)
    has_moonshard = (
        random.random() < (0.3 if position == 0 else 0.1) if level >= 25 else False
    )

    return {
        "account_id": account_id,
        "player_slot": player_slot,
        "team_number": team_number,
        "team_slot": team_slot,
        "hero_id": random.choice(HERO_IDS),
        "hero_variant": random.randint(1, 3),
        "item_0": items[0],
        "item_1": items[1],
        "item_2": items[2],
        "item_3": items[3],
        "item_4": items[4],
        "item_5": items[5],
        "backpack_0": 0,
        "backpack_1": 0,
        "backpack_2": 0,
        "item_neutral": random.choice(NEUTRAL_ITEMS),
        "item_neutral2": random.choice(NEUTRAL_ITEMS),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "leaver_status": 0,
        "last_hits": last_hits,
        "denies": denies,
        "gold_per_min": gpm,
        "xp_per_min": xpm,
        "level": level,
        "net_worth": net_worth,
        "aghanims_scepter": 1 if has_scepter else 0,
        "aghanims_shard": 1 if has_shard else 0,
        "moonshard": 1 if has_moonshard else 0,
        "hero_damage": hero_damage,
        "tower_damage": tower_damage,
        "hero_healing": hero_healing,
        "gold": gold,
        "gold_spent": gold_spent,
        "scaled_hero_damage": int(hero_damage * 0.4),
        "scaled_tower_damage": int(tower_damage * 0.4),
        "scaled_hero_healing": int(hero_healing * 0.6),
    }


def generate_mock_match(
    radiant_team: "Team",
    dire_team: "Team",
    match_id: int,
    match_seq_num: int,
    start_time: int,
    radiant_win: bool = None,
    league_id: int = None,
) -> dict:
    """
    Generate a mock Steam API match response.

    Matches the official Steam Web API GetMatchHistoryBySequenceNum format.

    Args:
        radiant_team: Team model instance for Radiant side
        dire_team: Team model instance for Dire side
        match_id: Unique match ID
        match_seq_num: Unique match sequence number
        start_time: Unix timestamp for match start
        radiant_win: If None, randomly determined
        league_id: Optional league ID

    Returns:
        Dict matching Steam API GetMatchHistoryBySequenceNum response format
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
                duration=duration,
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
                duration=duration,
            )
        )

    match_data = {
        "match_id": match_id,
        "match_seq_num": match_seq_num,
        "radiant_win": radiant_win,
        "duration": duration,
        "start_time": start_time,
        "game_mode": 2,  # Captain's Mode
        "lobby_type": 1,  # Practice (1) or Tournament (2)
        "human_players": 10,
        "players": players,
    }

    if league_id:
        match_data["league_id"] = league_id

    # Return in the format expected by process_match (wrapped in result)
    return {"result": match_data}


def generate_double_elim_bracket_matches(
    teams: list["Team"],
    base_match_id: int = 9000000001,
    base_match_seq_num: int = 7000000001,
    base_time: int = None,
    league_id: int = None,
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
        base_match_seq_num: Starting match sequence number
        base_time: Starting timestamp (defaults to now)
        league_id: Optional league ID to associate with matches

    Returns:
        List of mock match dicts in bracket order
    """
    if len(teams) < 4:
        raise ValueError("Need at least 4 teams for double elimination")

    if base_time is None:
        base_time = int(datetime.now().timestamp())

    matches = []
    match_id = base_match_id
    match_seq_num = base_match_seq_num
    current_time = base_time

    # Time between matches (1 hour)
    match_interval = 3600

    # Winners Round 1
    # Match 1: Team 0 vs Team 1
    match1 = generate_mock_match(
        radiant_team=teams[0],
        dire_team=teams[1],
        match_id=match_id,
        match_seq_num=match_seq_num,
        start_time=current_time,
        league_id=league_id,
    )
    matches.append(match1)
    w1_winner = teams[0] if match1["result"]["radiant_win"] else teams[1]
    w1_loser = teams[1] if match1["result"]["radiant_win"] else teams[0]
    match_id += 1
    match_seq_num += 1
    current_time += match_interval

    # Match 2: Team 2 vs Team 3
    match2 = generate_mock_match(
        radiant_team=teams[2],
        dire_team=teams[3],
        match_id=match_id,
        match_seq_num=match_seq_num,
        start_time=current_time,
        league_id=league_id,
    )
    matches.append(match2)
    w2_winner = teams[2] if match2["result"]["radiant_win"] else teams[3]
    w2_loser = teams[3] if match2["result"]["radiant_win"] else teams[2]
    match_id += 1
    match_seq_num += 1
    current_time += match_interval

    # Losers Round 1: Loser1 vs Loser2
    match3 = generate_mock_match(
        radiant_team=w1_loser,
        dire_team=w2_loser,
        match_id=match_id,
        match_seq_num=match_seq_num,
        start_time=current_time,
        league_id=league_id,
    )
    matches.append(match3)
    l1_winner = w1_loser if match3["result"]["radiant_win"] else w2_loser
    match_id += 1
    match_seq_num += 1
    current_time += match_interval

    # Winners Final: Winner1 vs Winner2
    match4 = generate_mock_match(
        radiant_team=w1_winner,
        dire_team=w2_winner,
        match_id=match_id,
        match_seq_num=match_seq_num,
        start_time=current_time,
        league_id=league_id,
    )
    matches.append(match4)
    wf_winner = w1_winner if match4["result"]["radiant_win"] else w2_winner
    wf_loser = w2_winner if match4["result"]["radiant_win"] else w1_winner
    match_id += 1
    match_seq_num += 1
    current_time += match_interval

    # Losers Final: L1 Winner vs WF Loser
    match5 = generate_mock_match(
        radiant_team=l1_winner,
        dire_team=wf_loser,
        match_id=match_id,
        match_seq_num=match_seq_num,
        start_time=current_time,
        league_id=league_id,
    )
    matches.append(match5)
    lf_winner = l1_winner if match5["result"]["radiant_win"] else wf_loser
    match_id += 1
    match_seq_num += 1
    current_time += match_interval

    # Grand Final: Winners Final Winner vs Losers Final Winner
    match6 = generate_mock_match(
        radiant_team=wf_winner,
        dire_team=lf_winner,
        match_id=match_id,
        match_seq_num=match_seq_num,
        start_time=current_time,
        league_id=league_id,
    )
    matches.append(match6)

    # Grand Final Reset (if losers bracket winner wins)
    if not match6["result"]["radiant_win"]:
        match_id += 1
        match_seq_num += 1
        current_time += match_interval
        match7 = generate_mock_match(
            radiant_team=wf_winner,
            dire_team=lf_winner,
            match_id=match_id,
            match_seq_num=match_seq_num,
            start_time=current_time,
            league_id=league_id,
        )
        matches.append(match7)

    return matches


def generate_mock_matches_for_tournament(
    tournament: "Tournament",
    league_id: int = None,
) -> list[dict]:
    """
    Generate mock Steam matches for a tournament's bracket.

    Args:
        tournament: Tournament instance with teams
        league_id: Optional league ID to associate with matches

    Returns:
        List of mock match dicts ready to be saved
    """
    teams = list(tournament.teams.all()[:4])

    if len(teams) < 4:
        raise ValueError(f"Tournament needs at least 4 teams, has {len(teams)}")

    # Use tournament date as base time
    if tournament.date_played:
        # Convert date to datetime if needed
        if hasattr(tournament.date_played, "timestamp"):
            base_time = int(tournament.date_played.timestamp())
        else:
            # date object - convert to datetime
            from datetime import time

            dt = datetime.combine(tournament.date_played, time(12, 0, 0))
            base_time = int(dt.timestamp())
    else:
        base_time = int(datetime.now().timestamp())

    return generate_double_elim_bracket_matches(
        teams=teams,
        base_match_id=9000000001,
        base_match_seq_num=7000000001,
        base_time=base_time,
        league_id=league_id,
    )


def generate_mock_match_history_response(matches: list[dict]) -> dict:
    """
    Generate a mock GetMatchHistory API response from a list of matches.

    This is useful for testing the league sync flow where GetMatchHistory
    is called first to get the list of matches.

    Args:
        matches: List of match dicts (from generate_mock_match or similar)

    Returns:
        Dict matching Steam API GetMatchHistory response format
    """
    history_matches = []

    for match_data in matches:
        result = match_data.get("result", match_data)
        players = []

        for player in result.get("players", []):
            players.append(
                {
                    "account_id": player["account_id"],
                    "player_slot": player["player_slot"],
                    "team_number": player.get(
                        "team_number", 0 if player["player_slot"] < 128 else 1
                    ),
                    "team_slot": player.get("team_slot", player["player_slot"] % 128),
                    "hero_id": player["hero_id"],
                    "hero_variant": player.get("hero_variant", 1),
                }
            )

        history_matches.append(
            {
                "match_id": result["match_id"],
                "match_seq_num": result.get("match_seq_num", result["match_id"]),
                "start_time": result["start_time"],
                "lobby_type": result.get("lobby_type", 1),
                "radiant_team_id": 0,  # Would need team info
                "dire_team_id": 0,
                "players": players,
            }
        )

    return {
        "result": {
            "status": 1,
            "num_results": len(history_matches),
            "total_results": len(history_matches),
            "results_remaining": 0,
            "matches": history_matches,
        }
    }
