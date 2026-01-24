"""API views for Captain's Mode hero draft."""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.broadcast import broadcast_herodraft_event
from app.functions.herodraft import (
    get_available_heroes,
    submit_choice,
    submit_pick,
    trigger_roll,
)
from app.models import DraftTeam, Game, HeroDraft, HeroDraftEvent, HeroDraftState
from app.serializers import HeroDraftEventSerializer, HeroDraftSerializer

log = logging.getLogger(__name__)


def _get_draft_with_prefetch(draft_pk: int) -> HeroDraft:
    """Get a draft with all related data prefetched for serialization."""
    return HeroDraft.objects.prefetch_related(
        "draft_teams__tournament_team__captain",
        "draft_teams__tournament_team__members",
        "rounds",
    ).get(pk=draft_pk)


def _get_draft_team_for_user(draft: HeroDraft, user) -> DraftTeam | None:
    """Get the DraftTeam for a user in this draft, if they are a captain."""
    for draft_team in draft.draft_teams.all():
        if draft_team.captain and draft_team.captain.pk == user.pk:
            return draft_team
    return None


def _user_is_captain_in_draft(draft: HeroDraft, user) -> bool:
    """Check if the user is a captain in this draft."""
    return _get_draft_team_for_user(draft, user) is not None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_herodraft(request, game_pk):
    """
    Create a new hero draft for a game.

    The game must have both radiant_team and dire_team assigned.
    Creates the HeroDraft and two DraftTeam objects.

    Returns:
        201: Created draft data
        400: Game already has a draft or missing teams
        404: Game not found
    """
    game = get_object_or_404(Game, pk=game_pk)

    # Check if draft already exists - return existing draft instead of error
    if hasattr(game, "herodraft"):
        draft = _get_draft_with_prefetch(game.herodraft.pk)
        return Response(HeroDraftSerializer(draft).data, status=status.HTTP_200_OK)

    # Check game has both teams
    if not game.radiant_team or not game.dire_team:
        return Response(
            {"error": "Game must have both radiant and dire teams assigned"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check both teams have captains
    if not game.radiant_team.captain or not game.dire_team.captain:
        return Response(
            {"error": "Both teams must have captains assigned"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create the draft
    draft = HeroDraft.objects.create(
        game=game, state=HeroDraftState.WAITING_FOR_CAPTAINS
    )

    # Create draft teams
    DraftTeam.objects.create(draft=draft, tournament_team=game.radiant_team)
    DraftTeam.objects.create(draft=draft, tournament_team=game.dire_team)

    log.info(f"Created HeroDraft {draft.pk} for game {game.pk}")

    # Create event
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="captain_connected",
        metadata={"created_by": request.user.pk},
    )

    broadcast_herodraft_event(draft, "draft_created")

    # Refetch with prefetch for proper serialization
    draft = _get_draft_with_prefetch(draft.pk)
    return Response(HeroDraftSerializer(draft).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_herodraft(request, draft_pk):
    """
    Get the current state of a hero draft.

    Returns:
        200: Draft data
        404: Draft not found
    """
    draft = _get_draft_with_prefetch(draft_pk)
    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_ready(request, draft_pk):
    """
    Mark a captain as ready.

    The user must be a captain in this draft.
    When both captains are ready, the draft state transitions to "rolling".

    Returns:
        200: Updated draft data
        403: User is not a captain in this draft
        404: Draft not found
        400: Invalid state for this operation
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    if draft.state != HeroDraftState.WAITING_FOR_CAPTAINS:
        return Response(
            {"error": f"Cannot set ready in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    draft_team = _get_draft_team_for_user(draft, request.user)
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN,
        )

    draft_team.is_ready = True
    draft_team.is_connected = True
    draft_team.save()

    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="captain_ready",
        draft_team=draft_team,
        metadata={"captain_id": request.user.pk},
    )

    # Check if both teams are ready
    all_ready = all(t.is_ready for t in draft.draft_teams.all())
    if all_ready:
        draft.state = HeroDraftState.ROLLING
        draft.save()
        log.info(f"HeroDraft {draft.pk} transitioning to rolling state")

    broadcast_herodraft_event(draft, "captain_ready", draft_team)

    draft = _get_draft_with_prefetch(draft.pk)
    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def do_trigger_roll(request, draft_pk):
    """
    Trigger the coin flip to determine who chooses first.

    The draft must be in "rolling" state.
    The user must be a captain in this draft.

    Returns:
        200: Updated draft data with roll winner
        403: User is not a captain in this draft
        404: Draft not found
        400: Invalid state for this operation
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    if draft.state != HeroDraftState.ROLLING:
        return Response(
            {"error": f"Cannot trigger roll in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    draft_team = _get_draft_team_for_user(draft, request.user)
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Perform the roll
    winner = trigger_roll(draft, draft_team)

    log.info(
        f"HeroDraft {draft.pk} roll triggered by team {draft_team.pk}, winner: {winner.pk}"
    )

    broadcast_herodraft_event(draft, "roll_result", winner)

    # Refetch with prefetch for proper serialization
    draft = _get_draft_with_prefetch(draft.pk)
    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def do_submit_choice(request, draft_pk):
    """
    Submit a choice for pick order or side.

    The roll winner chooses first (pick_order or side).
    The other team gets the remaining choice.

    Request body:
        choice_type: "pick_order" or "side"
        value: "first"/"second" for pick_order, "radiant"/"dire" for side

    Returns:
        200: Updated draft data
        403: User is not a captain or not their turn to choose
        404: Draft not found
        400: Invalid state, choice type, or value
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    if draft.state != HeroDraftState.CHOOSING:
        return Response(
            {"error": f"Cannot submit choice in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    draft_team = _get_draft_team_for_user(draft, request.user)
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN,
        )

    choice_type = request.data.get("choice_type")
    value = request.data.get("value")

    # Validate choice_type
    if choice_type not in ["pick_order", "side"]:
        return Response(
            {"error": "choice_type must be 'pick_order' or 'side'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate value based on choice_type
    if choice_type == "pick_order" and value not in ["first", "second"]:
        return Response(
            {"error": "value must be 'first' or 'second' for pick_order"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if choice_type == "side" and value not in ["radiant", "dire"]:
        return Response(
            {"error": "value must be 'radiant' or 'dire' for side"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Determine who can make which choice
    # Roll winner chooses first - they pick either pick_order or side
    # The other team then gets the remaining choice
    is_roll_winner = draft.roll_winner and draft.roll_winner.pk == draft_team.pk

    # Check if choice is already made
    if choice_type == "pick_order":
        if draft_team.is_first_pick is not None:
            return Response(
                {"error": "Pick order already chosen"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    elif choice_type == "side":
        if draft_team.is_radiant is not None:
            return Response(
                {"error": "Side already chosen"}, status=status.HTTP_400_BAD_REQUEST
            )

    # Roll winner must make first choice
    other_team = draft.draft_teams.exclude(pk=draft_team.pk).first()
    if is_roll_winner:
        # Roll winner makes first choice (either pick_order or side)
        pass
    else:
        # Non-winner can only choose if winner already made a choice
        # Safety check: roll_winner should exist if we're in choosing state
        if not draft.roll_winner:
            return Response(
                {"error": "Roll winner not set"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        winner_made_choice = (
            draft.roll_winner.is_first_pick is not None
            or draft.roll_winner.is_radiant is not None
        )
        if not winner_made_choice:
            return Response(
                {"error": "Roll winner must choose first"},
                status=status.HTTP_403_FORBIDDEN,
            )

    submit_choice(draft, draft_team, choice_type, value)

    log.info(
        f"HeroDraft {draft.pk} choice submitted: {choice_type}={value} by team {draft_team.pk}"
    )

    broadcast_herodraft_event(draft, "choice_made", draft_team)

    # Refetch with prefetch for proper serialization
    draft = _get_draft_with_prefetch(draft.pk)

    # Start tick broadcaster if draft just entered drafting state
    if draft.state == HeroDraftState.DRAFTING:
        from app.tasks.herodraft_tick import start_tick_broadcaster

        start_tick_broadcaster(draft.id)

    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def do_submit_pick(request, draft_pk):
    """
    Submit a hero pick or ban for the current round.

    Request body:
        hero_id: int - The hero ID to pick/ban

    Returns:
        200: Updated draft data
        403: User is not a captain or not their turn
        404: Draft not found
        400: Invalid state, hero already picked, or invalid hero
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    if draft.state != HeroDraftState.DRAFTING:
        return Response(
            {"error": f"Cannot submit pick in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    draft_team = _get_draft_team_for_user(draft, request.user)
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN,
        )

    hero_id = request.data.get("hero_id")
    if hero_id is None:
        return Response(
            {"error": "hero_id is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        hero_id = int(hero_id)
    except (ValueError, TypeError):
        return Response(
            {"error": "hero_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Check hero is available
    available = get_available_heroes(draft)
    if hero_id not in available:
        return Response(
            {"error": "Hero is not available (already picked or banned)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        completed_round = submit_pick(draft, draft_team, hero_id)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    log.info(
        f"HeroDraft {draft.pk} pick submitted: hero {hero_id} by team {draft_team.pk} (round {completed_round.round_number})"
    )

    broadcast_herodraft_event(draft, "hero_selected", draft_team)

    # Refetch with prefetch for proper serialization
    draft = _get_draft_with_prefetch(draft.pk)
    return Response(HeroDraftSerializer(draft).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_events(request, draft_pk):
    """
    List all events for a hero draft.

    Returns:
        200: List of events
        404: Draft not found
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    events = draft.events.all()
    return Response(HeroDraftEventSerializer(events, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_available_heroes(request, draft_pk):
    """
    List all heroes that are still available (not picked or banned).

    Returns:
        200: List of available hero IDs
        404: Draft not found
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    available = get_available_heroes(draft)
    return Response({"available_heroes": available})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def abandon_draft(request, draft_pk):
    """
    Abandon a hero draft.

    Can be called by an admin or a captain in the draft.
    Transitions the draft to "abandoned" state.

    Returns:
        200: Updated draft data
        403: User is not authorized to abandon this draft
        404: Draft not found
        400: Draft already completed or abandoned
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    # Check if draft is already in a terminal state
    if draft.state in (HeroDraftState.COMPLETED, HeroDraftState.ABANDONED):
        return Response(
            {"error": f"Cannot abandon draft in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check authorization: must be admin or captain in this draft
    is_captain = _user_is_captain_in_draft(draft, request.user)
    is_admin = request.user.is_staff

    if not is_captain and not is_admin:
        return Response(
            {"error": "You are not authorized to abandon this draft"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Transition to abandoned state
    draft.state = HeroDraftState.ABANDONED
    draft.save()

    log.info(
        f"HeroDraft {draft.pk} abandoned by user {request.user.pk} (admin={is_admin})"
    )

    # Create event for audit trail
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="draft_abandoned",
        metadata={"abandoned_by": request.user.pk, "was_admin": is_admin},
    )

    broadcast_herodraft_event(draft, "draft_abandoned")

    draft = _get_draft_with_prefetch(draft.pk)
    return Response(HeroDraftSerializer(draft).data)
