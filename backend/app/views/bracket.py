"""Bracket API views for tournament bracket management."""

from cacheops import invalidate_model, invalidate_obj
from django.db import transaction
from django.db.models import Max
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from app.models import Game, Team, Tournament
from app.permissions_org import (
    can_edit_tournament,
    can_manage_game,
    has_league_admin_access,
    has_league_staff_access,
)
from app.serializers import (
    BracketGameSerializer,
    BracketGenerateSerializer,
    BracketSaveSerializer,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_bracket(request, tournament_id):
    """Get bracket structure for a tournament."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
        )

    games = (
        Game.objects.filter(tournament=tournament)
        .select_related(
            "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
        )
        .order_by("bracket_type", "round", "position")
    )

    serializer = BracketGameSerializer(games, many=True)
    return Response({"tournamentId": tournament_id, "matches": serializer.data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_bracket(request, tournament_id):
    """Generate bracket structure from tournament teams.

    Requires league admin access to the tournament's league.
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check permission
    if not can_edit_tournament(request.user, tournament):
        return Response(
            {
                "error": "You do not have permission to generate brackets for this tournament"
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = BracketGenerateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
@permission_classes([IsAuthenticated])
@transaction.atomic
def save_bracket(request, tournament_id):
    """Save bracket structure to database.

    Requires league admin access to the tournament's league.
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check permission
    if not can_edit_tournament(request.user, tournament):
        return Response(
            {
                "error": "You do not have permission to save brackets for this tournament"
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = BracketSaveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    matches = serializer.validated_data["matches"]

    # Delete existing bracket games for this tournament
    Game.objects.filter(tournament=tournament).delete()

    # Pass 1: Create all games without FK relationships
    # Map frontend ID -> database PK
    id_to_game = {}

    for match in matches:
        game = Game.objects.create(
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

        # Set teams if provided
        radiant_team = match.get("radiantTeam")
        if radiant_team and radiant_team.get("pk"):
            game.radiant_team_id = radiant_team["pk"]

        dire_team = match.get("direTeam")
        if dire_team and dire_team.get("pk"):
            game.dire_team_id = dire_team["pk"]

        game.save()
        id_to_game[match["id"]] = game

    # Pass 2: Wire up FK relationships
    for match in matches:
        game = id_to_game[match["id"]]
        updated = False

        next_match_id = match.get("nextMatchId")
        if next_match_id and next_match_id in id_to_game:
            game.next_game = id_to_game[next_match_id]
            updated = True

        loser_next_match_id = match.get("loserNextMatchId")
        if loser_next_match_id and loser_next_match_id in id_to_game:
            game.loser_next_game = id_to_game[loser_next_match_id]
            updated = True

        if updated:
            game.save()

    # Return saved games
    saved_games = Game.objects.filter(tournament=tournament).select_related(
        "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
    )
    result_serializer = BracketGameSerializer(saved_games, many=True)

    # Invalidate caches after saving bracket
    invalidate_model(Game)
    invalidate_obj(tournament)

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
@permission_classes([IsAuthenticated])
@transaction.atomic
def advance_winner(request, game_id):
    """Mark winner and advance to next match, setting placement if eliminated.

    Requires league staff access.
    """
    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response({"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check permission
    if not can_manage_game(request.user, game):
        return Response(
            {"error": "You do not have permission to manage this game"},
            status=status.HTTP_403_FORBIDDEN,
        )

    winner_slot = request.data.get("winner")  # 'radiant' or 'dire'
    if winner_slot not in ["radiant", "dire"]:
        return Response(
            {"error": "Invalid winner slot"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Validate team exists in the slot
    if winner_slot == "radiant":
        if not game.radiant_team:
            return Response(
                {"error": "No radiant team assigned"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        winning_team = game.radiant_team
        losing_team = game.dire_team
    else:
        if not game.dire_team:
            return Response(
                {"error": "No dire team assigned"}, status=status.HTTP_400_BAD_REQUEST
            )
        winning_team = game.dire_team
        losing_team = game.radiant_team

    game.winning_team = winning_team
    game.status = "completed"
    game.save()

    # Advance winner to next game if exists
    if game.next_game and game.next_game_slot:
        next_game = game.next_game
        if game.next_game_slot == "radiant":
            next_game.radiant_team = winning_team
        else:
            next_game.dire_team = winning_team
        next_game.save()

    # Handle loser path
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
        else:
            # No loser path - team is eliminated, set placement
            placement = calculate_placement(game)
            if placement:
                losing_team.placement = placement
                losing_team.save()

    # Grand finals - also set winner's placement
    if game.bracket_type == "grand_finals":
        winning_team.placement = 1
        winning_team.save()

    # Invalidate caches after advancing winner
    invalidate_model(Game)
    invalidate_model(Team)

    return Response(BracketGameSerializer(game).data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def set_team_placement(request, tournament_id, team_id):
    """Manually set or clear a team's tournament placement.

    Requires league staff access.
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check permission - use tournament's league for staff check
    if not can_edit_tournament(request.user, tournament):
        return Response(
            {
                "error": "You do not have permission to set placements in this tournament"
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        team = Team.objects.get(pk=team_id, tournament=tournament)
    except Team.DoesNotExist:
        return Response(
            {"error": "Team not found in this tournament"},
            status=status.HTTP_404_NOT_FOUND,
        )

    placement = request.data.get("placement")

    # Validate placement
    if placement is not None:
        if not isinstance(placement, int) or placement < 1:
            return Response(
                {"error": "Placement must be a positive integer or null"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    team.placement = placement
    team.save()

    # Invalidate caches after setting placement
    invalidate_obj(team)
    invalidate_model(Team)

    return Response({"team_id": team.pk, "placement": team.placement})
