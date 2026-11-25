"""Team placements derived from a tournament's bracket results (#843).

Placement rules, applied to the loser of every decided game it cannot come
back from (no losers-bracket path):

* Grand finals: winner 1st, loser 2nd.
* Losers bracket (double elimination): ``losers_bracket_placement``.
* Single-elimination winners bracket: a loser ``k`` rounds before the final
  places ``2**k + 1`` (final 2nd, semis 3rd, quarters 5th, round of 16 9th),
  the top of the tied range. The final's winner is 1st.
* Swiss games have no elimination and never set a placement.

``apply_bracket_placements`` runs after a write to a tournament's games. It
writes a team's placement only when the derived value changed across the
write, or the team is out but has no placement yet, so manual tie-breaks of
teams the write didn't affect survive.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from django.db.models import Max

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from telemetry.logging import get_logger
from tournament.models import Game, Team
from tournament.services.team_management import live_conflicts, roster_conflict_body

log = get_logger(__name__)

_BRACKET_ORDER: dict[str, int] = {"winners": 0, "losers": 1, "grand_finals": 2}


class PlacementRosterConflict(Exception):
    """Clearing `team`'s placement would put `users` on two live teams."""

    def __init__(
        self, team: Team, users: Sequence[CustomUser], body: dict[str, Any]
    ) -> None:
        super().__init__(body["error"])
        self.team = team
        self.user_ids: list[int] = [u.pk for u in users]
        self.body = body


def losers_bracket_placement(game_round: int, max_losers_round: int | None) -> int:
    if max_losers_round is None:
        return 3
    rounds_from_final = max_losers_round - game_round
    if rounds_from_final == 0:
        return 3
    if rounds_from_final <= 2:
        return 4
    base = 5
    for i in range(rounds_from_final - 3):
        base += 2**i
    return base


def single_elimination_placement(game_round: int, max_winners_round: int) -> int:
    return 2 ** (max_winners_round - game_round) + 1


def is_single_elimination_winners(game: Game) -> bool:
    return game.bracket_type == "winners" and game.elimination_type == "single"


def loser_is_eliminated(game: Game) -> bool:
    return not (game.elimination_type == "double" and game.loser_next_game_id)


def placement_for_loser(
    game: Game, max_losers_round: int | None, max_winners_round: int | None
) -> int | None:
    if game.bracket_type == "grand_finals":
        return 2
    if game.bracket_type == "losers":
        return losers_bracket_placement(game.round, max_losers_round)
    if is_single_elimination_winners(game) and max_winners_round is not None:
        return single_elimination_placement(game.round, max_winners_round)
    return None


def max_single_elimination_winners_round(tournament_id: int | None) -> int | None:
    return (
        Game.objects.nocache()
        .filter(
            tournament_id=tournament_id,
            bracket_type="winners",
            elimination_type="single",
        )
        .aggregate(Max("round"))["round__max"]
    )


def decides_tournament_winner(game: Game, max_winners_round: int | None) -> bool:
    return game.bracket_type == "grand_finals" or (
        is_single_elimination_winners(game) and game.round == max_winners_round
    )


def placement_for_game(game: Game) -> int | None:
    """Placement of this game's loser if the loss eliminates it, read from the DB."""
    if not loser_is_eliminated(game):
        return None
    max_losers_round = (
        Game.objects.nocache()
        .filter(tournament_id=game.tournament_id, bracket_type="losers")
        .aggregate(Max("round"))["round__max"]
    )
    return placement_for_loser(
        game, max_losers_round, max_single_elimination_winners_round(game.tournament_id)
    )


def compute_bracket_placements(games: Iterable[Game]) -> dict[int, int | None]:
    """Placement per team that appears in an elimination game (None = still in)."""
    elimination_games = sorted(
        (g for g in games if g.bracket_type in _BRACKET_ORDER),
        key=lambda g: (_BRACKET_ORDER[g.bracket_type], g.round, g.position),
    )
    max_losers_round = max(
        (g.round for g in elimination_games if g.bracket_type == "losers"),
        default=None,
    )
    max_winners_round = max(
        (g.round for g in elimination_games if is_single_elimination_winners(g)),
        default=None,
    )

    placements: dict[int, int | None] = {}
    for game in elimination_games:
        for team_id in (game.radiant_team_id, game.dire_team_id):
            if team_id is not None:
                placements.setdefault(team_id, None)

    for game in elimination_games:
        slots = {game.radiant_team_id, game.dire_team_id}
        if game.winning_team_id is None or game.winning_team_id not in slots:
            continue
        loser_id = next(
            (t for t in slots if t is not None and t != game.winning_team_id), None
        )
        if loser_id is not None and loser_is_eliminated(game):
            placement = placement_for_loser(game, max_losers_round, max_winners_round)
            if placement is not None:
                placements[loser_id] = placement
        if decides_tournament_winner(game, max_winners_round):
            placements[game.winning_team_id] = 1
    return placements


def tournament_bracket_placements(tournament_id: int | None) -> dict[int, int | None]:
    if tournament_id is None:
        return {}
    return compute_bracket_placements(
        Game.objects.nocache()
        .filter(tournament_id=tournament_id)
        .only(
            "pk",
            "bracket_type",
            "elimination_type",
            "round",
            "position",
            "radiant_team_id",
            "dire_team_id",
            "winning_team_id",
            "loser_next_game_id",
        )
    )


def apply_bracket_placements(
    tournament_id: int | None, before: dict[int, int | None]
) -> dict[int, int | None]:
    """Write placements that changed since ``before`` was taken; returns team_id -> new placement.

    Take ``before`` with ``tournament_bracket_placements`` ahead of the game
    writes and call this after them, inside the same transaction. Raises
    ``PlacementRosterConflict`` if a cleared placement would put a player on two
    live teams; the caller's transaction must roll back.
    """
    if tournament_id is None:
        return {}
    after = tournament_bracket_placements(tournament_id)
    candidates = set(before) | set(after)
    if not candidates:
        return {}
    changed: dict[int, int | None] = {}
    teams: list[Team] = []
    reopened: list[Team] = []
    for team in Team.objects.nocache().select_for_update().filter(pk__in=candidates):
        old, new = before.get(team.pk), after.get(team.pk)
        missing = new is not None and team.placement is None
        if (old == new and not missing) or team.placement == new:
            continue
        previous = team.placement
        team.placement = new
        team.save(update_fields=["placement"])
        changed[team.pk] = new
        teams.append(team)
        if previous is not None and new is None:
            reopened.append(team)
        log.info(
            "bracket_placement_derived",
            system="bracket",
            subsystem="placement",
            tournament_id=tournament_id,
            team_id=team.pk,
            previous_placement=previous,
            placement=new,
        )
    for team in sorted(reopened, key=lambda t: t.pk):
        conflicts = live_conflicts(team)
        if conflicts:
            log.warning(
                "bracket_placement_clear_blocked_roster_conflict",
                system="bracket",
                subsystem="placement",
                tournament_id=tournament_id,
                team_id=team.pk,
                user_ids=[u.pk for u in conflicts],
            )
            raise PlacementRosterConflict(
                team, conflicts, roster_conflict_body(team, conflicts)
            )
    if teams:
        invalidate_after_commit(*teams)
    return changed
