"""
Test endpoints for HeroDraft E2E testing (TEST ONLY).

These endpoints are only available when TEST_ENDPOINTS=true in settings.
"""

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.models import DraftTeam, Game, HeroDraft, HeroDraftEvent
from app.serializers import HeroDraftSerializer
from common.utils import isTestEnvironment

# Test key to tournament/game mapping for herodraft scenarios
# Uses existing bracket games from Real Tournament 38:
# - Winners Final (round 2, winners): vrm.mtl's Team vs ethan0688_'s Team
HERODRAFT_TEST_KEYS = {
    # Use Real Tournament 38's Winners Final (round 2, winners bracket)
    # vrm.mtl's Team vs ethan0688_'s Team
    "waiting_phase": {
        "tournament_name": "Real Tournament 38",
        "round": 2,
        "bracket_type": "winners",
        "position": 0,
        "initial_state": "waiting_for_captains",
    },
    "rolling_phase": {
        "tournament_name": "Real Tournament 38",
        "round": 2,
        "bracket_type": "winners",
        "position": 0,
        "initial_state": "rolling",
    },
    "choosing_phase": {
        "tournament_name": "Real Tournament 38",
        "round": 2,
        "bracket_type": "winners",
        "position": 0,
        "initial_state": "choosing",
    },
    "drafting_phase": {
        "tournament_name": "Real Tournament 38",
        "round": 2,
        "bracket_type": "winners",
        "position": 0,
        "initial_state": "drafting",
    },
    # Two-captain full draft test - uses Winners Final game
    # vrm.mtl's Team vs ethan0688_'s Team (both have captains)
    "two_captain_test": {
        "tournament_name": "Real Tournament 38",
        "round": 2,
        "bracket_type": "winners",
        "position": 0,
        "initial_state": "waiting_for_captains",
    },
    # Demo HeroDraft Tournament - for video recording demos
    # Uses Demo Team Alpha vs Demo Team Beta
    "demo_herodraft": {
        "tournament_name": "Demo HeroDraft Tournament",
        "round": 1,
        "bracket_type": "winners",
        "position": 0,
        "initial_state": "waiting_for_captains",
    },
}


@api_view(["POST"])
@authentication_classes([])  # Disable authentication to bypass CSRF
@permission_classes([AllowAny])
def force_herodraft_timeout(request, draft_pk):
    """
    Force a timeout on the current active round (TEST ONLY).

    This immediately triggers the timeout logic which:
    1. Selects a random available hero
    2. Completes the current round
    3. Advances to the next round (or completes the draft)
    4. Logs a round_timeout event

    Used for testing timeout behavior without waiting 30+ seconds.

    Args:
        draft_pk: The HeroDraft primary key

    Returns:
        200: Updated draft data after timeout
        400: No active round to timeout
        404: Draft not found
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    if draft.state != "drafting":
        return Response(
            {"error": f"Cannot force timeout in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    current_round = draft.rounds.filter(state="active").first()
    if not current_round:
        return Response(
            {"error": "No active round to timeout"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Import and call the timeout handler
    from app.broadcast import broadcast_herodraft_state
    from app.functions.herodraft import auto_random_pick

    try:
        completed_round = auto_random_pick(draft, current_round.draft_team)
    except Exception as e:
        return Response(
            {"error": f"Timeout handling failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Refresh and broadcast the state update to WebSocket clients
    draft.refresh_from_db()
    broadcast_herodraft_state(draft, "round_timeout")

    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
@authentication_classes([])  # Disable authentication to bypass CSRF
@permission_classes([AllowAny])
def reset_herodraft(request, draft_pk):
    """
    Reset a hero draft back to waiting_for_captains state (TEST ONLY).

    This allows re-running E2E tests without recreating the draft.
    Deletes all rounds and events, resets team states.

    Args:
        draft_pk: The HeroDraft primary key

    Returns:
        200: Reset draft data
        404: Draft not found
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    # Delete all rounds
    draft.rounds.all().delete()

    # Delete all events
    draft.events.all().delete()

    # Reset draft state
    draft.state = "waiting_for_captains"
    draft.roll_winner = None
    draft.save()

    # Reset draft teams
    for draft_team in draft.draft_teams.all():
        draft_team.is_ready = False
        draft_team.is_connected = False
        draft_team.is_first_pick = None
        draft_team.is_radiant = None
        draft_team.reserve_time_remaining = 90000  # 90 seconds default
        draft_team.save()

    # Log reset event
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="draft_reset",
        metadata={"reset_by": "test_endpoint"},
    )

    return Response(HeroDraftSerializer(draft).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_herodraft_by_key(request, key: str):
    """
    Get or create a HeroDraft for a test scenario (TEST ONLY).

    This endpoint finds the game for the test key and creates/returns
    a HeroDraft in the specified initial state. If a draft already exists,
    it returns the existing one.

    Path params:
        key: str - Test scenario key (e.g., 'waiting_phase', 'drafting_phase')

    Returns:
        200: HeroDraft data with draft_teams including captain info
        404: Unknown key or game not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Tournament

    config = HERODRAFT_TEST_KEYS.get(key)
    if not config:
        return Response(
            {
                "error": f"Unknown herodraft test key: {key}. Available: {list(HERODRAFT_TEST_KEYS.keys())}"
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Find the tournament
    try:
        tournament = Tournament.objects.get(name=config["tournament_name"])
    except Tournament.DoesNotExist:
        return Response(
            {
                "error": f"Tournament '{config['tournament_name']}' not found. Run populate first."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Find the game
    game_filter = {
        "tournament": tournament,
        "round": config["round"],
        "bracket_type": config["bracket_type"],
    }

    # Add position filter if specified (for specific game lookup)
    if "position" in config:
        game_filter["position"] = config["position"]

    # If specific teams are required, find game with those teams
    if "teams" in config:
        from app.models import Team

        team_names = config["teams"]
        teams = Team.objects.filter(tournament=tournament, name__in=team_names)
        if teams.count() >= 2:
            team_list = list(teams)
            # Find game where these teams are radiant/dire
            game = Game.objects.filter(
                **game_filter,
                radiant_team__in=team_list,
                dire_team__in=team_list,
            ).first()
        else:
            game = None
    else:
        game = Game.objects.filter(**game_filter).first()

    if not game:
        return Response(
            {
                "error": f"Game not found in {config['tournament_name']} round {config['round']} {config['bracket_type']}"
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if game has both teams with captains
    if not game.radiant_team or not game.dire_team:
        return Response(
            {"error": "Game must have both radiant and dire teams"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not game.radiant_team.captain or not game.dire_team.captain:
        return Response(
            {"error": "Both teams must have captains"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get or create the HeroDraft
    if hasattr(game, "herodraft"):
        draft = game.herodraft
    else:
        draft = HeroDraft.objects.create(
            game=game,
            state=config["initial_state"],
        )
        # Create draft teams
        DraftTeam.objects.create(draft=draft, tournament_team=game.radiant_team)
        DraftTeam.objects.create(draft=draft, tournament_team=game.dire_team)

    # Set up the draft to the requested initial state
    _setup_draft_state(draft, config["initial_state"])

    # Prefetch for serialization
    draft = HeroDraft.objects.prefetch_related(
        "draft_teams__tournament_team__captain",
        "draft_teams__tournament_team__members",
        "rounds",
    ).get(pk=draft.pk)

    # Return with extra fields for test setup
    data = HeroDraftSerializer(draft).data

    # Add game and tournament info for URL construction
    data["game"] = {
        "pk": game.pk,
        "tournament_pk": game.tournament.pk if game.tournament else None,
        "radiant_team_name": game.radiant_team.name if game.radiant_team else None,
        "dire_team_name": game.dire_team.name if game.dire_team else None,
    }

    data["draft_teams"] = [
        {
            "id": dt.pk,
            "captain": (
                {
                    "pk": dt.tournament_team.captain.pk,
                    "username": dt.tournament_team.captain.username,
                    "discordId": dt.tournament_team.captain.discordId,
                }
                if dt.tournament_team.captain
                else None
            ),
            "team_name": dt.tournament_team.name,
            "is_ready": dt.is_ready,
            "is_radiant": dt.is_radiant,
            "is_first_pick": dt.is_first_pick,
        }
        for dt in draft.draft_teams.all()
    ]

    return Response(data)


def _setup_draft_state(draft: HeroDraft, target_state: str) -> None:
    """
    Set up a draft to reach the target state for testing.

    This resets the draft and configures it to the specified state.
    """
    from app.functions.herodraft import build_draft_rounds, trigger_roll

    # Reset to clean state first
    draft.rounds.all().delete()
    draft.events.all().delete()
    draft.roll_winner = None

    # Reset draft teams
    for dt in draft.draft_teams.all():
        dt.is_ready = False
        dt.is_connected = False
        dt.is_first_pick = None
        dt.is_radiant = None
        dt.reserve_time_remaining = 90000
        dt.save()

    if target_state == "waiting_for_captains":
        draft.state = "waiting_for_captains"
        draft.save()
        return

    # For rolling state: both captains ready
    if target_state in ("rolling", "choosing", "drafting"):
        for dt in draft.draft_teams.all():
            dt.is_ready = True
            dt.is_connected = True
            dt.save()

    if target_state == "rolling":
        draft.state = "rolling"
        draft.save()
        return

    # For choosing state: roll has been done
    if target_state in ("choosing", "drafting"):
        first_team = draft.draft_teams.first()
        if first_team:
            trigger_roll(draft, first_team)
            # Refresh draft from DB to get updated roll_winner
            draft.refresh_from_db()

    if target_state == "choosing":
        # trigger_roll already sets state to "choosing", no need to save again
        return

    # For drafting state: choices have been made
    if target_state == "drafting":
        teams = list(draft.draft_teams.all())
        if len(teams) >= 2:
            # Roll winner chooses pick order
            winner = draft.roll_winner or teams[0]
            loser = teams[1] if winner == teams[0] else teams[0]

            winner.is_first_pick = True
            winner.save()
            loser.is_first_pick = False
            loser.save()

            # Loser gets side choice
            loser.is_radiant = True
            loser.save()
            winner.is_radiant = False
            winner.save()

        # Build draft rounds
        build_draft_rounds(draft)
        draft.state = "drafting"
        draft.save()
