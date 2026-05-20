"""Bracket API views for tournament bracket management."""

from app.cache_utils import invalidate_obj
from django.db import transaction
from django.db.models import Max
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit
from app.models import Game, Team, Tournament
from app.permissions_org import IsTournamentStaff
from app.serializers import (
    BracketGameSerializer,
    BracketGenerateSerializer,
    BracketSaveSerializer,
)
from telemetry.logging import get_logger

log = get_logger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_bracket(request, tournament_id):
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

    games = (
        Game.objects.filter(tournament=tournament)
        .select_related(
            "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
        )
        .order_by("bracket_type", "round", "position")
    )

    serializer = BracketGameSerializer(games, many=True)
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
def generate_bracket(request, tournament_id):
    """Generate bracket structure from tournament teams.

    Requires league staff access to the tournament's league.
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
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


@api_view(["POST"])
@permission_classes([IsTournamentStaff])
@transaction.atomic
def save_bracket(request, tournament_id):
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
            # Create new game
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

        # Set teams if provided
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
                missing_next_targets.append(
                    {"from": match["id"], "to": next_match_id}
                )

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
    )

    # Return saved games
    saved_games = Game.objects.filter(tournament=tournament).select_related(
        "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
    )
    result_serializer = BracketGameSerializer(saved_games, many=True)

    # Invalidate caches after saving bracket
    invalidate_after_commit(*saved_games, tournament)

    return Response({"tournamentId": tournament_id, "matches": result_serializer.data})


def calculate_placement(game):
    """
    Calculate placement for a team eliminated from this game.

    Returns placement number or None if team isn't eliminated
    (e.g., winners bracket losers go to losers bracket).
    """
    # Grand finals loser = 2nd place
    if game.bracket_type == "grand_finals":
        return 2

    # Losers bracket elimination
    if game.bracket_type == "losers":
        # Find max losers round for this tournament
        max_round = Game.objects.filter(
            tournament=game.tournament,
            bracket_type="losers",
        ).aggregate(Max("round"))["round__max"]

        if max_round is None:
            return 3  # Only one losers game = losers finals

        rounds_from_final = max_round - game.round

        if rounds_from_final == 0:  # Losers finals
            return 3
        elif rounds_from_final <= 2:  # Losers semi (4th)
            return 4
        else:
            # Each earlier round: 5th-6th, 7th-8th, etc.
            base = 5
            for i in range(rounds_from_final - 3):
                base += 2**i
            return base

    # Winners bracket elimination → goes to losers (no placement yet)
    return None


@api_view(["POST"])
@permission_classes([IsTournamentStaff])
@transaction.atomic
def advance_winner(request, game_id):
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

    # Handle unset case
    if winner is None:
        if game.winning_team:
            # Find losing team to clear their placement
            losing_team = (
                game.dire_team
                if game.winning_team == game.radiant_team
                else game.radiant_team
            )
            if losing_team and losing_team.placement:
                losing_team.placement = None
                losing_team.save()

        game.winning_team = None
        game.status = "scheduled"
        game.save()
        log.info(
            "bracket_winner_unset",
            system="bracket",
            subsystem="advance",
            game_id=game.pk,
            tournament_id=game.tournament_id,
            bracket_type=game.bracket_type,
        )
        return Response(BracketGameSerializer(game).data)

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
    placement_set = None
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
        else:
            # No loser path - team is eliminated, set placement
            placement = calculate_placement(game)
            if placement:
                losing_team.placement = placement
                losing_team.save()
                placement_set = placement

    # Grand finals - also set winner's placement
    if game.bracket_type == "grand_finals":
        winning_team.placement = 1
        winning_team.save()

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
        placement_set=placement_set,
        elimination_type=game.elimination_type,
    )

    # Invalidate caches after advancing winner
    objs_to_invalidate = [game, winning_team]
    if losing_team:
        objs_to_invalidate.append(losing_team)
    if game.tournament:
        objs_to_invalidate.append(game.tournament)
    invalidate_after_commit(*objs_to_invalidate)

    return Response(BracketGameSerializer(game).data)


@api_view(["PATCH"])
@permission_classes([IsTournamentStaff])
def set_team_placement(request, tournament_id, team_id):
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

    # Validate placement
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

    previous_placement = team.placement
    team.placement = placement
    team.save()

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

    # Invalidate caches after setting placement
    invalidate_obj(team)
    if tournament:
        invalidate_obj(tournament)

    return Response({"team_id": team.pk, "placement": team.placement})
