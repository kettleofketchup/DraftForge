"""Bracket API views for tournament bracket management."""

from django.db import transaction
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from draft.models import HeroDraft
from events.overrides import REASON_MAX_LENGTH
from lobby.models import GameLobby
from telemetry.logging import get_logger
from tournament.models import Game, Team, Tournament
from tournament.models.team_log import TeamLogAction, TeamLogVia
from tournament.permissions import IsTournamentStaff
from tournament.serializers.game import (
    BracketGameSerializer,
    BracketGenerateSerializer,
    BracketSaveSerializer,
)
from tournament.serializers.users import TEAM_USER_INDEX, build_team_user_index
from tournament.services.bracket_placement import (
    apply_bracket_placements,
    decides_tournament_winner,
    max_single_elimination_winners_round,
    placement_for_game,
    tournament_bracket_placements,
)
from tournament.services.team_audit import log_snapshot_fields, write_team_log
from tournament.services.team_management import live_conflicts, roster_conflict_body

log = get_logger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_bracket(request: Request, tournament_id: int) -> Response:
    """Get bracket structure for a tournament."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        log.warning(
            "bracket_load_tournament_missing",
            system="bracket",
            subsystem="load",
            tournament_id=tournament_id,
        )
        return Response(
            {"error": "Tournament not found", "code": "tournament_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # cacheops would key this on app_game only and serve stale select_related teams.
    games = (
        Game.objects.nocache()
        .filter(tournament=tournament)
        .select_related(
            "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
        )
        .prefetch_related(
            Prefetch(
                "lobbies",
                queryset=GameLobby.objects.only("id", "game_id", "state", "created_at"),
                to_attr="latest_lobbies",
            ),
            Prefetch("herodraft", queryset=HeroDraft.objects.only("id", "game_id")),
        )
        .order_by("bracket_type", "round", "position")
    )

    teams = [
        team
        for game in games
        for team in (game.radiant_team, game.dire_team, game.winning_team)
        if team is not None
    ]
    serializer = BracketGameSerializer(
        games,
        many=True,
        context={TEAM_USER_INDEX: build_team_user_index(tournament, teams)},
    )
    log.debug(
        "bracket_loaded",
        system="bracket",
        subsystem="load",
        tournament_id=tournament_id,
        match_count=len(serializer.data),
    )
    return Response({"tournamentId": tournament_id, "matches": serializer.data})


@api_view(["POST"])
@permission_classes([IsTournamentStaff])
def generate_bracket(request: Request, tournament_id: int) -> Response:
    """Generate bracket structure from tournament teams.

    Requires league staff access to the tournament's league.
    """
    try:
        Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found", "code": "tournament_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = BracketGenerateSerializer(data=request.data)
    if not serializer.is_valid():
        log.warning(
            "bracket_generate_invalid_payload",
            system="bracket",
            subsystem="generate",
            tournament_id=tournament_id,
            errors=serializer.errors,
        )
        return Response(
            {
                "error": "Invalid bracket generation payload",
                "code": "invalid_payload",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # TODO: Implement bracket generation logic
    # For now, return empty bracket structure
    return Response(
        {
            "tournamentId": tournament_id,
            "matches": [],
            "message": "Bracket generation placeholder",
        }
    )


def _foreign_team_ids(tournament: Tournament, matches: list[dict]) -> list[int]:
    requested: set[int] = set()
    for match in matches:
        for slot in ("radiantTeam", "direTeam"):
            team = match.get(slot)
            if isinstance(team, dict) and team.get("pk"):
                requested.add(team["pk"])
    if not requested:
        return []
    own = set(
        Team.objects.nocache()
        .filter(tournament=tournament, pk__in=requested)
        .values_list("pk", flat=True)
    )
    return sorted(requested - own)


@api_view(["POST"])
@permission_classes([IsTournamentStaff])
@transaction.atomic
def save_bracket(request: Request, tournament_id: int) -> Response:
    """Save bracket structure to database.

    Requires league staff access to the tournament's league.
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        log.warning(
            "bracket_save_tournament_missing",
            system="bracket",
            subsystem="save",
            tournament_id=tournament_id,
        )
        return Response(
            {"error": "Tournament not found", "code": "tournament_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = BracketSaveSerializer(data=request.data)
    if not serializer.is_valid():
        log.warning(
            "bracket_save_invalid_payload",
            system="bracket",
            subsystem="save",
            tournament_id=tournament_id,
            errors=serializer.errors,
        )
        return Response(
            {
                "error": "Invalid bracket payload",
                "code": "invalid_payload",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    matches = serializer.validated_data["matches"]
    foreign_team_ids = _foreign_team_ids(tournament, matches)
    if foreign_team_ids:
        log.warning(
            "bracket_save_foreign_teams",
            system="bracket",
            subsystem="save",
            tournament_id=tournament_id,
            team_ids=foreign_team_ids,
        )
        return Response(
            {
                "error": "Bracket references teams that are not in this tournament",
                "code": "team_not_in_tournament",
                "team_ids": foreign_team_ids,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    placements_before = tournament_bracket_placements(tournament.pk)

    # Build lookup of existing games by (bracket_type, round, position)
    existing_games = {
        (g.bracket_type, g.round, g.position): g
        for g in Game.objects.filter(tournament=tournament)
    }

    # Track which existing games are still in the new bracket
    seen_keys = set()

    # Pass 1: Create or update games (without FK relationships)
    # Map frontend ID -> database Game
    id_to_game = {}
    created_count = 0
    updated_count = 0

    for match in matches:
        key = (
            match.get("bracketType", "winners"),
            match.get("round", 1),
            match.get("position", 0),
        )
        seen_keys.add(key)

        existing = existing_games.get(key)
        if existing:
            # Update existing game (preserves PK and related HeroDraft)
            game = existing
            game.elimination_type = match.get("eliminationType", "double")
            game.status = match.get("status", game.status)
            game.next_game_slot = match.get("nextMatchSlot")
            game.loser_next_game_slot = match.get("loserNextMatchSlot")
            game.swiss_record_wins = match.get("swissRecordWins", 0)
            game.swiss_record_losses = match.get("swissRecordLosses", 0)
            updated_count += 1
        else:
            game = Game(
                tournament=tournament,
                round=match.get("round", 1),
                position=match.get("position", 0),
                bracket_type=match.get("bracketType", "winners"),
                elimination_type=match.get("eliminationType", "double"),
                status=match.get("status", "pending"),
                next_game_slot=match.get("nextMatchSlot"),
                loser_next_game_slot=match.get("loserNextMatchSlot"),
                swiss_record_wins=match.get("swissRecordWins", 0),
                swiss_record_losses=match.get("swissRecordLosses", 0),
            )
            created_count += 1

        radiant_team = match.get("radiantTeam")
        game.radiant_team_id = (
            radiant_team["pk"] if radiant_team and radiant_team.get("pk") else None
        )

        dire_team = match.get("direTeam")
        game.dire_team_id = (
            dire_team["pk"] if dire_team and dire_team.get("pk") else None
        )

        # Persist the winning team from the FE's `winner` field
        # ('radiant' | 'dire' | None). Without this, clicking "Set Winner"
        # in the match modal and then Save would store status='completed'
        # but leave winning_team=NULL — mapApiMatchToMatch can't derive
        # match.winner on reload, the bracket card loses its green check,
        # and the row goes "stuck" (covered by issue #235).
        winner_slot = match.get("winner")
        if winner_slot == "radiant":
            game.winning_team_id = game.radiant_team_id
        elif winner_slot == "dire":
            game.winning_team_id = game.dire_team_id
        else:
            game.winning_team_id = None

        # Clear next_game/loser_next_game before pass 2 rewires them
        game.next_game = None
        game.loser_next_game = None
        game.save()
        id_to_game[match["id"]] = game

    # Delete games that are no longer in the bracket
    deleted_count = 0
    for key, game in existing_games.items():
        if key not in seen_keys:
            game.delete()
            deleted_count += 1

    # Pass 2: Wire up FK relationships
    wired_next = 0
    wired_loser_next = 0
    missing_next_targets = []
    missing_loser_next_targets = []
    for match in matches:
        game = id_to_game[match["id"]]
        updated = False

        next_match_id = match.get("nextMatchId")
        if next_match_id:
            if next_match_id in id_to_game:
                game.next_game = id_to_game[next_match_id]
                wired_next += 1
                updated = True
            else:
                missing_next_targets.append({"from": match["id"], "to": next_match_id})

        loser_next_match_id = match.get("loserNextMatchId")
        if loser_next_match_id:
            if loser_next_match_id in id_to_game:
                game.loser_next_game = id_to_game[loser_next_match_id]
                wired_loser_next += 1
                updated = True
            else:
                missing_loser_next_targets.append(
                    {"from": match["id"], "to": loser_next_match_id}
                )

        if updated:
            game.save()

    if missing_next_targets or missing_loser_next_targets:
        # Dangling references aren't fatal (FKs stay null), but they almost
        # always mean the frontend serialized a stale/orphan link — surface
        # it so we can fix the source rather than silently corrupting the
        # bracket flow.
        log.warning(
            "bracket_save_dangling_refs",
            system="bracket",
            subsystem="save",
            tournament_id=tournament_id,
            missing_next=missing_next_targets,
            missing_loser_next=missing_loser_next_targets,
        )

    placements_changed = apply_bracket_placements(tournament.pk, placements_before)

    log.info(
        "bracket_saved",
        system="bracket",
        subsystem="save",
        tournament_id=tournament_id,
        match_count=len(matches),
        created=created_count,
        updated=updated_count,
        deleted=deleted_count,
        wired_next=wired_next,
        wired_loser_next=wired_loser_next,
        placements_changed=placements_changed,
    )

    saved_games = Game.objects.filter(tournament=tournament).select_related(
        "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
    )
    result_serializer = BracketGameSerializer(saved_games, many=True)

    invalidate_after_commit(*saved_games, tournament)

    return Response({"tournamentId": tournament_id, "matches": result_serializer.data})


def calculate_placement(game: Game) -> int | None:
    """Placement for a team eliminated from this game, or None if it isn't out."""
    return placement_for_game(game)


def _unset_winner(game: Game) -> Response:
    """Clear a game's result and pull its advanced teams back out of downstream slots."""
    winning_team = game.winning_team
    losing_team: Team | None = None
    if winning_team is not None:
        if winning_team.pk == game.radiant_team_id:
            losing_team = game.dire_team
        elif winning_team.pk == game.dire_team_id:
            losing_team = game.radiant_team

    teams_to_reset = [losing_team]
    if decides_tournament_winner(
        game, max_single_elimination_winners_round(game.tournament_id)
    ):
        teams_to_reset.append(winning_team)
    reopening = [t for t in teams_to_reset if t is not None and t.placement is not None]
    for team in reopening:
        conflicts = live_conflicts(team, reopening=reopening)
        if conflicts:
            log.warning(
                "bracket_unset_blocked_roster_conflict",
                system="bracket",
                subsystem="advance",
                game_id=game.pk,
                tournament_id=game.tournament_id,
                team_id=team.pk,
                user_ids=[u.pk for u in conflicts],
            )
            return Response(
                roster_conflict_body(team, conflicts, reopening=reopening),
                status=status.HTTP_409_CONFLICT,
            )

    to_clear: list[tuple[Game, str]] = []
    for target, slot, team in (
        (game.next_game, game.next_game_slot, winning_team),
        (game.loser_next_game, game.loser_next_game_slot, losing_team),
    ):
        if target is None or slot not in ("radiant", "dire") or team is None:
            continue
        if getattr(target, f"{slot}_team_id") != team.pk:
            continue
        if target.status == "completed":
            log.warning(
                "bracket_unset_blocked_downstream_completed",
                system="bracket",
                subsystem="advance",
                game_id=game.pk,
                downstream_game_id=target.pk,
            )
            return Response(
                {
                    "error": "A later match with this team is already completed; unset it first",
                    "code": "downstream_match_completed",
                    "details": {"downstream_game_id": target.pk},
                },
                status=status.HTTP_409_CONFLICT,
            )
        to_clear.append((target, slot))

    placements_before = tournament_bracket_placements(game.tournament_id)
    for target, slot in to_clear:
        setattr(target, f"{slot}_team", None)
        target.save()

    game.winning_team = None
    game.status = "pending"
    game.save()
    placements_changed = apply_bracket_placements(game.tournament_id, placements_before)

    log.info(
        "bracket_winner_unset",
        system="bracket",
        subsystem="advance",
        game_id=game.pk,
        tournament_id=game.tournament_id,
        bracket_type=game.bracket_type,
        cleared_downstream=[t.pk for t, _ in to_clear],
        placements_changed=placements_changed,
    )

    invalidate_after_commit(
        game,
        *(t for t, _ in to_clear),
        *([game.tournament] if game.tournament else []),
    )
    return Response(BracketGameSerializer(game).data)


@api_view(["POST"])
@permission_classes([IsTournamentStaff])
@transaction.atomic
def advance_winner(request: Request, game_id: int) -> Response:
    """Mark winner and advance to next match, setting placement if eliminated.

    Requires league staff access.
    """
    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        log.warning(
            "bracket_advance_game_missing",
            system="bracket",
            subsystem="advance",
            game_id=game_id,
        )
        return Response(
            {"error": "Game not found", "code": "game_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    winner = request.data.get("winner")

    if winner is None:
        return _unset_winner(game)

    winner_slot = winner  # 'radiant' or 'dire'
    if winner_slot not in ["radiant", "dire"]:
        log.warning(
            "bracket_advance_invalid_winner",
            system="bracket",
            subsystem="advance",
            game_id=game.pk,
            received=winner_slot,
        )
        return Response(
            {
                "error": "Invalid winner slot",
                "code": "invalid_winner",
                "details": {
                    "received": winner_slot,
                    "allowed": ["radiant", "dire"],
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate team exists in the slot
    if winner_slot == "radiant":
        if not game.radiant_team:
            log.warning(
                "bracket_advance_missing_team",
                system="bracket",
                subsystem="advance",
                game_id=game.pk,
                slot="radiant",
            )
            return Response(
                {
                    "error": "No radiant team assigned",
                    "code": "missing_radiant_team",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        winning_team = game.radiant_team
        losing_team = game.dire_team
    else:
        if not game.dire_team:
            log.warning(
                "bracket_advance_missing_team",
                system="bracket",
                subsystem="advance",
                game_id=game.pk,
                slot="dire",
            )
            return Response(
                {
                    "error": "No dire team assigned",
                    "code": "missing_dire_team",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        winning_team = game.dire_team
        losing_team = game.radiant_team

    placements_before = tournament_bracket_placements(game.tournament_id)
    game.winning_team = winning_team
    game.status = "completed"
    game.save()

    # Advance winner to next game if exists
    winner_advanced_to = None
    if game.next_game and game.next_game_slot:
        next_game = game.next_game
        if game.next_game_slot == "radiant":
            next_game.radiant_team = winning_team
        else:
            next_game.dire_team = winning_team
        next_game.save()
        winner_advanced_to = next_game.pk
    elif game.next_game and not game.next_game_slot:
        log.warning(
            "bracket_advance_next_slot_missing",
            system="bracket",
            subsystem="advance",
            game_id=game.pk,
            next_game_id=game.next_game_id,
        )

    # Handle loser path
    loser_advanced_to = None
    if losing_team:
        if (
            game.elimination_type == "double"
            and game.loser_next_game
            and game.loser_next_game_slot
        ):
            # Advance loser to losers bracket
            loser_game = game.loser_next_game
            if game.loser_next_game_slot == "radiant":
                loser_game.radiant_team = losing_team
            else:
                loser_game.dire_team = losing_team
            loser_game.save()
            loser_advanced_to = loser_game.pk
        elif (
            game.elimination_type == "double"
            and game.loser_next_game
            and not game.loser_next_game_slot
        ):
            # Dangling loser FK with no slot — losing team would be orphaned.
            # Surface it; a follow-up save_bracket should re-wire the slot.
            log.warning(
                "bracket_advance_loser_slot_missing",
                system="bracket",
                subsystem="advance",
                game_id=game.pk,
                loser_next_game_id=game.loser_next_game_id,
            )

    placements_changed = apply_bracket_placements(game.tournament_id, placements_before)

    log.info(
        "bracket_winner_advanced",
        system="bracket",
        subsystem="advance",
        game_id=game.pk,
        tournament_id=game.tournament_id,
        bracket_type=game.bracket_type,
        round=game.round,
        position=game.position,
        winning_team_id=winning_team.pk,
        losing_team_id=losing_team.pk if losing_team else None,
        winner_advanced_to=winner_advanced_to,
        loser_advanced_to=loser_advanced_to,
        placements_changed=placements_changed,
        elimination_type=game.elimination_type,
    )

    objs_to_invalidate = [game, winning_team]
    if losing_team:
        objs_to_invalidate.append(losing_team)
    if game.tournament:
        objs_to_invalidate.append(game.tournament)
    invalidate_after_commit(*objs_to_invalidate)

    return Response(BracketGameSerializer(game).data)


@api_view(["PATCH"])
@permission_classes([IsTournamentStaff])
def set_team_placement(request: Request, tournament_id: int, team_id: int) -> Response:
    """Manually set or clear a team's tournament placement.

    Requires league staff access.
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found", "code": "tournament_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        team = Team.objects.get(pk=team_id, tournament=tournament)
    except Team.DoesNotExist:
        return Response(
            {
                "error": "Team not found in this tournament",
                "code": "team_not_found",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    placement = request.data.get("placement")

    if placement is not None:
        if not isinstance(placement, int) or placement < 1:
            log.warning(
                "bracket_placement_invalid",
                system="bracket",
                subsystem="placement",
                tournament_id=tournament_id,
                team_id=team_id,
                received=placement,
            )
            return Response(
                {
                    "error": "Placement must be a positive integer or null",
                    "code": "invalid_placement",
                    "details": {"received": placement},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    reason = request.data.get("reason", "")
    if not isinstance(reason, str) or len(reason.strip()) > REASON_MAX_LENGTH:
        return Response(
            {
                "error": f"Reason must be text of at most {REASON_MAX_LENGTH} characters",
                "code": "invalid_reason",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    reason = reason.strip()

    previous_placement = team.placement
    if placement is None and previous_placement is not None:
        conflicts = live_conflicts(team)
        if conflicts:
            log.warning(
                "bracket_placement_blocked_roster_conflict",
                system="bracket",
                subsystem="placement",
                tournament_id=tournament_id,
                team_id=team.pk,
                user_ids=[u.pk for u in conflicts],
            )
            return Response(
                roster_conflict_body(team, conflicts),
                status=status.HTTP_409_CONFLICT,
            )
    with transaction.atomic():
        team.placement = placement
        team.save()
        if placement != previous_placement:
            write_team_log(
                team,
                snapshot=log_snapshot_fields(team),
                action=TeamLogAction.SET_PLACEMENT,
                via=TeamLogVia.WEB,
                actor=request.user,
                reason=reason,
                details={
                    "before": {"placement": previous_placement},
                    "after": {"placement": placement},
                },
            )

    log.info(
        "bracket_placement_set",
        system="bracket",
        subsystem="placement",
        tournament_id=tournament_id,
        team_id=team.pk,
        previous_placement=previous_placement,
        placement=placement,
        manual=True,
    )

    invalidate_obj(team)
    if tournament:
        invalidate_obj(tournament)

    return Response({"team_id": team.pk, "placement": team.placement})
