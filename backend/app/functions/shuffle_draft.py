"""Shuffle draft logic - lowest MMR picks first."""

import random
from typing import Optional


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


def build_shuffle_rounds(draft) -> None:
    """
    Create all rounds for shuffle draft, assign first captain.

    Args:
        draft: Draft model instance
    """
    from app.models import DraftRound

    teams = list(draft.tournament.teams.all())
    num_teams = len(teams)
    total_picks = num_teams * 4

    # Create all rounds with null captains
    rounds = [
        DraftRound(
            draft=draft,
            captain=None,
            pick_number=i,
            pick_phase=(i - 1) // num_teams + 1,
        )
        for i in range(1, total_picks + 1)
    ]
    DraftRound.objects.bulk_create(rounds)

    # Assign first captain based on lowest captain MMR
    first_team, tie_data = get_lowest_mmr_team(teams)
    first_round = draft.draft_rounds.order_by("pick_number").first()
    first_round.captain = first_team.captain
    if tie_data:
        first_round.was_tie = True
        first_round.tie_roll_data = tie_data
    first_round.save()


def assign_next_shuffle_captain(draft) -> Optional[dict]:
    """
    After a pick, assign captain to next round.

    Args:
        draft: Draft model instance

    Returns:
        tie_resolution data if tie occurred, else None
    """
    next_round = (
        draft.draft_rounds.filter(captain__isnull=True).order_by("pick_number").first()
    )
    if not next_round:
        return None

    teams = list(draft.tournament.teams.all())
    next_team, tie_data = get_lowest_mmr_team(teams)

    next_round.captain = next_team.captain
    if tie_data:
        next_round.was_tie = True
        next_round.tie_roll_data = tie_data
    next_round.save()

    return tie_data
