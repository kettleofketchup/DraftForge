"""Version token for a tournament's bracket, used to refuse stale Saves."""

import hashlib
from collections.abc import Iterable

from tournament.models import Game

_VERSION_FIELDS = (
    "pk",
    "bracket_type",
    "round",
    "position",
    "elimination_type",
    "status",
    "radiant_team_id",
    "dire_team_id",
    "winning_team_id",
    "next_game_id",
    "next_game_slot",
    "loser_next_game_id",
    "loser_next_game_slot",
    "swiss_record_wins",
    "swiss_record_losses",
)


def bracket_version(games: Iterable[Game]) -> str:
    """Token over the fields save_bracket writes; any change to them changes it."""
    rows = sorted(
        "|".join(str(getattr(game, field)) for field in _VERSION_FIELDS)
        for game in games
    )
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()[:32]
