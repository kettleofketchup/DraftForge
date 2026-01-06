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

    # TODO: Implement bracket saving logic
    return Response(
        {"tournamentId": tournament_id, "message": "Bracket save placeholder"}
    )


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
