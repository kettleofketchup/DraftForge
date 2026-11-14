"""Move a tournament to `past` when its bracket final is decided (#419)."""

from django.db import transaction

from app.cache_utils import invalidate_after_commit
from app.models import Game, Tournament
from telemetry.logging import get_logger

log = get_logger(__name__)

PAST = "past"
IN_PROGRESS = "in_progress"


def find_final_game(tournament_id: int) -> Game | None:
    """The game whose winner decides the tournament, if the bracket has one.

    Double elimination: the last grand finals game. Winners-only (single
    elimination): the one game with no next game. Swiss has no final.
    """
    games = list(
        Game.objects.nocache()
        .filter(tournament_id=tournament_id)
        .only(
            "pk", "bracket_type", "round", "position", "next_game_id", "winning_team_id"
        )
    )
    grand_finals = [g for g in games if g.bracket_type == "grand_finals"]
    if grand_finals:
        return max(grand_finals, key=lambda g: (g.round, g.position))
    if any(g.bracket_type != "winners" for g in games):
        return None
    terminal = [g for g in games if g.next_game_id is None]
    return terminal[0] if len(terminal) == 1 else None


def sync_tournament_completion(
    tournament_id: int, *, cleared_game_id: int | None = None
) -> str | None:
    """Mark the tournament past once its final has a winner.

    Never moves a tournament backwards, except when ``cleared_game_id`` is the
    final whose winner was just removed: then a past tournament reopens to
    in_progress. Returns the new state, or None when nothing changed.
    """
    final = find_final_game(tournament_id)
    if final is None:
        return None

    if final.winning_team_id is not None:
        to_state, reason = PAST, "final_decided"
    elif cleared_game_id == final.pk:
        to_state, reason = IN_PROGRESS, "final_result_cleared"
    else:
        return None

    with transaction.atomic():
        tournament = (
            Tournament.objects.nocache()
            .select_for_update()
            .filter(pk=tournament_id)
            .first()
        )
        if tournament is None:
            return None
        from_state = tournament.state
        if to_state == PAST and from_state == PAST:
            return None
        if to_state == IN_PROGRESS and from_state != PAST:
            return None
        tournament.state = to_state
        tournament.save(update_fields=["state"])
        invalidate_after_commit(tournament)

    log.info(
        "tournament_state_changed",
        system="tournament",
        subsystem="completion",
        tournament_id=tournament_id,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        final_game_id=final.pk,
        winning_team_id=final.winning_team_id,
    )
    return to_state
