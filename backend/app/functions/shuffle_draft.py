"""Shuffle draft logic - lowest MMR picks first."""

import random


def get_team_total_mmr(team) -> int:
    """
    Calculate total MMR for a team (captain + members).

    Args:
        team: Team model instance

    Returns:
        Total MMR as integer
    """
    total = team.captain.mmr or 0 if team.captain else 0
    for member in team.members.exclude(id=team.captain_id):
        total += member.mmr or 0
    return total


def roll_until_winner(teams: list) -> tuple:
    """
    Roll dice until one winner emerges.

    Args:
        teams: List of Team model instances

    Returns:
        Tuple of (winner_team, roll_rounds)
        roll_rounds is list of rounds, each round is list of {"team_id": N, "roll": N}
    """
    roll_rounds = []
    remaining = list(teams)

    while len(remaining) > 1:
        rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
        roll_rounds.append(rolls)

        max_roll = max(r["roll"] for r in rolls)
        remaining = [
            t
            for t in remaining
            if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll
        ]

    return remaining[0], roll_rounds


def get_lowest_mmr_team(teams: list) -> tuple:
    """
    Find team with lowest total MMR.

    Args:
        teams: List of Team model instances

    Returns:
        Tuple of (winner_team, tie_resolution_data or None)
    """
    team_mmrs = [(team, get_team_total_mmr(team)) for team in teams]
    min_mmr = min(mmr for _, mmr in team_mmrs)
    tied = [t for t, mmr in team_mmrs if mmr == min_mmr]

    if len(tied) > 1:
        winner, roll_rounds = roll_until_winner(tied)
        tie_data = {
            "tied_teams": [
                {"id": t.id, "name": t.name, "mmr": get_team_total_mmr(t)} for t in tied
            ],
            "roll_rounds": roll_rounds,
            "winner_id": winner.id,
        }
        return winner, tie_data

    return tied[0], None
