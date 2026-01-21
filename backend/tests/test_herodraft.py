"""
Test endpoints for HeroDraft E2E testing (TEST ONLY).

These endpoints are only available when TEST_ENDPOINTS=true in settings.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from app.models import HeroDraft, HeroDraftEvent
from app.serializers import HeroDraftSerializer


@api_view(["POST"])
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
    from app.functions.herodraft import auto_random_pick

    try:
        auto_random_pick(draft, current_round.draft_team)
    except Exception as e:
        return Response(
            {"error": f"Timeout handling failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Refresh and return updated draft
    draft.refresh_from_db()
    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
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
