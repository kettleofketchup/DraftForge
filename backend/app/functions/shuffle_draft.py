"""Shuffle draft logic - lowest MMR picks first."""


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
