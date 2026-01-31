"""
Test endpoints for Demo tournament reset (TEST ONLY).

These endpoints are only available when TEST_ENDPOINTS=true in settings.
Used by `inv demo.*` tasks to reset demo data before recording videos.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.utils import isTestEnvironment

# Demo tournament names (must match populate.py)
DEMO_TOURNAMENTS = {
    "demo_herodraft": "Demo HeroDraft Tournament",
    "demo_captaindraft": "Demo Captain Draft Tournament",
    "demo_snake_draft": "Demo Snake Draft Tournament",
    "demo_shuffle_draft": "Demo Shuffle Draft Tournament",
}


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_demo_tournament(request, key: str):
    """
    Reset a demo tournament to its initial state (TEST ONLY).

    This endpoint resets the tournament data for clean demo recordings:
    - demo_herodraft: Resets HeroDraft to waiting_for_captains
    - demo_captaindraft: Resets Draft to pending, clears teams

    Args:
        key: Demo tournament key (demo_herodraft or demo_captaindraft)

    Returns:
        200: Reset successful with tournament info
        404: Unknown key or tournament not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Draft, DraftTeam, Game, HeroDraft, Team, Tournament

    tournament_name = DEMO_TOURNAMENTS.get(key)
    if not tournament_name:
        return Response(
            {
                "error": f"Unknown demo key: {key}. Available: {list(DEMO_TOURNAMENTS.keys())}"
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        tournament = Tournament.objects.get(name=tournament_name)
    except Tournament.DoesNotExist:
        return Response(
            {
                "error": f"Tournament '{tournament_name}' not found. Run 'inv db.populate.all' first."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if key == "demo_herodraft":
        return _reset_demo_herodraft(tournament)
    elif key == "demo_captaindraft":
        return _reset_demo_captaindraft(tournament)
    elif key == "demo_snake_draft":
        return _reset_demo_draft(tournament, "snake")
    elif key == "demo_shuffle_draft":
        return _reset_demo_draft(tournament, "shuffle")

    return Response(
        {"error": "Reset not implemented for this key"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _reset_demo_herodraft(tournament):
    """Reset HeroDraft tournament to initial state."""
    from app.models import DraftTeam, Game, HeroDraft, HeroDraftEvent, HeroDraftRound

    # Find the game and herodraft
    game = tournament.games.first()
    if not game:
        return Response(
            {"error": "No game found for demo herodraft tournament"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    herodraft = getattr(game, "herodraft", None)
    if not herodraft:
        return Response(
            {"error": "No HeroDraft found for game"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Delete all rounds and events
    herodraft.rounds.all().delete()
    herodraft.events.all().delete()

    # Reset draft state
    herodraft.state = "waiting_for_captains"
    herodraft.roll_winner = None
    herodraft.paused_at = None
    herodraft.save()

    # Reset draft teams
    for draft_team in herodraft.draft_teams.all():
        draft_team.is_ready = False
        draft_team.is_connected = False
        draft_team.is_first_pick = None
        draft_team.is_radiant = None
        draft_team.reserve_time_remaining = 90000
        draft_team.save()

    # Reset game status
    game.status = "pending"
    game.winning_team = None
    game.save()

    return Response(
        {
            "status": "reset",
            "tournament": tournament.name,
            "tournament_pk": tournament.pk,
            "herodraft_pk": herodraft.pk,
            "herodraft_state": herodraft.state,
        }
    )


def _reset_demo_captaindraft(tournament):
    """Reset Captain Draft tournament to initial state."""
    from app.models import Draft, Team

    # Delete all teams (captain draft creates them)
    tournament.teams.all().delete()

    # Reset tournament state
    tournament.state = "signup"
    tournament.save()

    # Find and reset the draft
    draft = Draft.objects.filter(tournament=tournament).first()
    if draft:
        # Clear draft state
        draft.state = "pending"
        draft.current_round = 0
        draft.current_pick = 0
        draft.save()

        # Clear draft events
        draft.events.all().delete()

    return Response(
        {
            "status": "reset",
            "tournament": tournament.name,
            "tournament_pk": tournament.pk,
            "draft_pk": draft.pk if draft else None,
            "draft_state": draft.state if draft else None,
            "players": tournament.users.count(),
        }
    )


def _reset_demo_draft(tournament, draft_style: str):
    """Reset Snake/Shuffle Draft tournament to initial state.

    Clears all draft rounds and resets draft to pending state.
    Teams and captains are preserved (they're created during populate).
    """
    from app.models import Draft, DraftRound

    # Find and reset the draft
    draft = Draft.objects.filter(tournament=tournament).first()
    if not draft:
        return Response(
            {"error": "No draft found for tournament"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Clear all draft rounds (picks)
    DraftRound.objects.filter(draft=draft).delete()

    # Rebuild rounds for fresh draft
    draft.build_rounds()

    return Response(
        {
            "status": "reset",
            "tournament": tournament.name,
            "tournament_pk": tournament.pk,
            "draft_pk": draft.pk,
            "draft_style": draft.draft_style,
            "teams": tournament.teams.count(),
            "players": tournament.users.count(),
        }
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def generate_demo_bracket(request, tournament_pk: int):
    """
    Generate bracket for a tournament (TEST ONLY).

    This endpoint wraps the bracket generation logic for test/demo use.

    Args:
        tournament_pk: Tournament primary key

    Returns:
        200: Bracket generated successfully
        404: Tournament not found
        400: Error generating bracket
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Tournament
    from bracket.models import TournamentBracket

    try:
        tournament = Tournament.objects.get(pk=tournament_pk)
    except Tournament.DoesNotExist:
        return Response(
            {"error": f"Tournament {tournament_pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        # Delete existing brackets
        tournament.brackets.all().delete()

        # Create and generate new bracket
        bracket = TournamentBracket.objects.create(tournament=tournament)
        bracket.generate_double_elimination_bracket()
        bracket.save()

        return Response(
            {
                "status": "generated",
                "tournament": tournament.name,
                "tournament_pk": tournament.pk,
                "bracket_pk": bracket.pk,
            }
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_demo_tournament(request, key: str):
    """
    Get demo tournament info by key (TEST ONLY).

    Args:
        key: Demo tournament key (demo_herodraft or demo_captaindraft)

    Returns:
        200: Tournament info with relevant draft data
        404: Unknown key or tournament not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Draft, Game, HeroDraft, Tournament
    from app.serializers import HeroDraftSerializer, TournamentSerializer

    tournament_name = DEMO_TOURNAMENTS.get(key)
    if not tournament_name:
        return Response(
            {
                "error": f"Unknown demo key: {key}. Available: {list(DEMO_TOURNAMENTS.keys())}"
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        tournament = Tournament.objects.get(name=tournament_name)
    except Tournament.DoesNotExist:
        return Response(
            {
                "error": f"Tournament '{tournament_name}' not found. Run 'inv db.populate.all' first."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    response_data = {
        "tournament": TournamentSerializer(tournament).data,
        "key": key,
    }

    if key == "demo_herodraft":
        game = tournament.games.first()
        if game and hasattr(game, "herodraft"):
            herodraft = game.herodraft
            response_data["herodraft"] = HeroDraftSerializer(herodraft).data
            response_data["game_pk"] = game.pk

    elif key == "demo_captaindraft":
        draft = Draft.objects.filter(tournament=tournament).first()
        if draft:
            response_data["draft_pk"] = draft.pk
            response_data["draft_state"] = draft.state
            response_data["draft_type"] = draft.draft_type

    elif key in ("demo_snake_draft", "demo_shuffle_draft"):
        draft = Draft.objects.filter(tournament=tournament).first()
        if draft:
            response_data["draft_pk"] = draft.pk
            response_data["draft_style"] = draft.draft_style
            response_data["teams"] = tournament.teams.count()

    return Response(response_data)
