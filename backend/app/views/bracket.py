"""Bracket API views for tournament bracket management."""

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from app.models import Game, Team, Tournament
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
@permission_classes([IsAdminUser])
def generate_bracket(request, tournament_id):
    """Generate bracket structure from tournament teams."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
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
@permission_classes([IsAdminUser])
@transaction.atomic
def save_bracket(request, tournament_id):
    """Save bracket structure to database."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
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

    return Response({"tournamentId": tournament_id, "matches": result_serializer.data})


@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def advance_winner(request, game_id):
    """Mark winner and advance to next match."""
    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response({"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND)

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
        game.winning_team = game.radiant_team
    else:
        if not game.dire_team:
            return Response(
                {"error": "No dire team assigned"}, status=status.HTTP_400_BAD_REQUEST
            )
        game.winning_team = game.dire_team

    game.status = "completed"
    game.save()

    # Advance winner to next game if exists
    if game.next_game and game.next_game_slot:
        next_game = game.next_game
        if game.next_game_slot == "radiant":
            next_game.radiant_team = game.winning_team
        else:
            next_game.dire_team = game.winning_team
        next_game.save()

    # Advance loser if elimination_type is 'double' and loser path exists
    if (
        game.elimination_type == "double"
        and game.loser_next_game
        and game.loser_next_game_slot
    ):
        losing_team = game.dire_team if winner_slot == "radiant" else game.radiant_team
        loser_game = game.loser_next_game
        if game.loser_next_game_slot == "radiant":
            loser_game.radiant_team = losing_team
        else:
            loser_game.dire_team = losing_team
        loser_game.save()

    return Response(BracketGameSerializer(game).data)
