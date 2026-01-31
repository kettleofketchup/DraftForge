import json
import logging

import requests
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from social_core.backends.oauth import BaseOAuth1, BaseOAuth2

# Create your views here.
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage
from social_django.utils import load_strategy, psa

from app.broadcast import broadcast_event
from app.models import CustomUser, Draft, DraftEvent, DraftRound, Team, Tournament
from app.permissions import IsStaff
from app.serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    DraftSerializerMMRs,
    GameSerializer,
    TeamSerializer,
    TournamentSerializer,
    UserSerializer,
)
from backend import settings

log = logging.getLogger(__name__)


class PickPlayerForRound(serializers.Serializer):
    draft_round_pk = serializers.IntegerField(required=True)
    user_pk = serializers.IntegerField(required=True)


from cacheops import invalidate_obj


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pick_player_for_round(request):
    """
    Pick a player for a draft round.

    Authorization: Staff can pick for any round. Captains can only pick
    for their own round (when they are the captain for that round).

    Request body:
        draft_round_pk: int - Primary key of the draft round
        user_pk: int - Primary key of the user to pick

    Returns:
        201: Success with updated tournament data
        400: Validation error
        403: Not authorized (not staff and not captain for this round)
        404: Draft round or user not found
        500: Error during pick
    """

    serializer = PickPlayerForRound(data=request.data)

    if serializer.is_valid():
        draft_round_pk = serializer.validated_data["draft_round_pk"]
        user_pk = serializer.validated_data["user_pk"]
    else:
        return Response(serializer.errors, status=400)

    try:
        draft_round = DraftRound.objects.get(pk=draft_round_pk)
    except DraftRound.DoesNotExist:
        return Response({"error": "Draft round not found"}, status=404)

    is_staff = request.user.is_staff
    is_captain_for_round = draft_round.captain == request.user

    if not (is_staff or is_captain_for_round):
        log.warning(
            f"User {request.user.username} attempted to pick for round {draft_round_pk} "
            f"but is not staff or captain (captain is {draft_round.captain.username})"
        )
        return Response(
            {"error": "Only staff or the captain for this round can make picks"},
            status=403,
        )

    # Authorization check: staff OR captain for this round
    try:
        user = CustomUser.objects.get(pk=user_pk)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    try:
        draft_round.pick_player(user)
    except Exception as e:
        logging.error(
            f"Error picking player for draft round {draft_round_pk}: {str(e)}"
        )
        return Response({"error": f"Failed to pick player. {str(e)}"}, status=500)

    draft = draft_round.draft
    draft.save()
    draft_round.save()

    # Create player_picked event
    team = draft_round.team
    captain = draft_round.captain
    picked_event = DraftEvent.objects.create(
        draft=draft,
        event_type="player_picked",
        actor=request.user,
        payload={
            "pick_number": draft_round.pick_number,
            "captain_id": captain.pk,
            "captain_name": captain.username,
            "captain_avatar_url": captain.avatarUrl,
            "picked_id": user.pk,
            "picked_name": user.username,
            "picked_avatar_url": user.avatarUrl,
            "team_id": team.pk if team else None,
            "team_name": team.name if team else None,
        },
    )
    broadcast_event(picked_event)

    # For shuffle draft, assign next captain
    tie_data = None
    if draft.draft_style == "shuffle" and draft.users_remaining.exists():
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        tie_data = assign_next_shuffle_captain(draft)

    try:
        tournament = draft_round.draft.tournament
    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)
    # Build response data
    response_data = TournamentSerializer(tournament).data
    if tie_data:
        response_data["tie_resolution"] = tie_data

    # Invalidate specific objects, not entire model caches
    invalidate_obj(tournament)
    if draft:
        invalidate_obj(draft)
    return Response(response_data, status=201)


class CreateTournamentTeamRequestSerializer(serializers.Serializer):
    tournament_pk = serializers.IntegerField(required=True)
    user_pk = serializers.IntegerField(required=True)
    draft_order = serializers.IntegerField(
        required=False,
        help_text="Optional draft order for the team in the tournament",
        default=0,
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def create_team_from_captain(request):
    serializer = CreateTournamentTeamRequestSerializer(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]
        user_pk = serializer.validated_data["user_pk"]
        draft_order = serializer.validated_data.get("draft_order", 0)
    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.get(pk=tournament_pk)
        user = CustomUser.objects.get(pk=user_pk)

    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

        # Create a new team and add the user as a member (or captain)
    try:
        draft = tournament.draft

    except Draft.DoesNotExist:
        pass  # No draft exists, continue
    if Team.objects.filter(tournament=tournament, captain=user).exists():
        if draft_order is 0:
            logging.debug(
                "User is already a captain in this tournament with a draft order"
            )
            return Response(
                TournamentSerializer(tournament).data,
                TournamentSerializer(tournament).data,
                status=201,
            )

        team = Team.objects.get(tournament=tournament, captain=user)
        team.draft_order = draft_order
        team.save()
        return Response(
            {
                "error": "User is already a captain in this tournament with a draft order"
            },
            status=201,
        )

    team = Team.objects.create(
        tournament=tournament,
        name=f"{user.username}'s Team",
        captain=user,
        draft_order=draft_order,
    )
    team.members.add(user)

    # Invalidate specific tournament after team creation
    invalidate_obj(tournament)
    invalidate_obj(team)

    return Response(TournamentSerializer(tournament).data, status=201)


class CreateDraftRounds(serializers.Serializer):
    tournament_pk = serializers.IntegerField(required=True)


@api_view(["POST"])
@permission_classes([IsStaff])
def generate_draft_rounds(request):
    serializer = CreateDraftRounds(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]

    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.get(pk=tournament_pk)

    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)

        # Create a new team and add the user as a member (or captain)

    try:
        draft = tournament.draft
    except Draft.DoesNotExist:
        log.debug(f"Draft doesn't exist for {tournament.pk}, creating new one")
        draft = Draft.objects.create(tournament=tournament)

    logging.debug(f"Initialization draft for tournament {tournament.name}")
    # IMPORTANT: rebuild_teams MUST be called BEFORE build_rounds
    # so that team MMR calculations use only captains, not old picks
    # Use clear_only=True to avoid re-adding old draft choices before restart
    draft.rebuild_teams(clear_only=True)
    draft.build_rounds()
    draft.save()
    tournament.draft = draft
    tournament.save()

    # Invalidate specific objects
    invalidate_obj(draft)
    invalidate_obj(tournament)

    return Response(TournamentSerializer(tournament).data, status=201)


@api_view(["POST"])
@permission_classes([IsStaff])
def rebuild_team(request):
    serializer = CreateDraftRounds(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]

    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.get(pk=tournament_pk)

    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)

        # Create a new team and add the user as a member (or captain)

    # Ensure draft exists
    try:
        draft = tournament.draft
        if not draft:
            logging.debug(f"Draft doesn't exist for {tournament.pk}, creating new one")
            draft = Draft.objects.create(tournament=tournament)
    except Draft.DoesNotExist:
        logging.debug(f"Draft doesn't exist for {tournament.pk}, creating new one")
        draft = Draft.objects.create(tournament=tournament)

    # IMPORTANT: rebuild_teams MUST be called BEFORE build_rounds
    # so that team MMR calculations use only captains, not old picks
    # Use clear_only=True when building new rounds to avoid re-adding old picks
    will_build_rounds = not draft.draft_rounds.exists()
    draft.rebuild_teams(clear_only=will_build_rounds)

    # Build rounds if they don't exist
    if will_build_rounds:
        logging.debug("Draft rounds do not exist, building them now")
        draft.build_rounds()
    else:
        logging.debug(f"Draft already exists for tournament {tournament.name}")

    draft.save()
    tournament.draft = draft
    tournament = Tournament.objects.get(pk=tournament_pk)
    data = TournamentSerializer(tournament).data
    log.debug(data)

    # Invalidate specific objects after rebuilding teams
    invalidate_obj(draft)
    invalidate_obj(tournament)

    return Response(data, status=201)


class DraftPredictMMRSerializer(serializers.Serializer):
    pk = serializers.IntegerField(required=True)


from cacheops import cached_as


@api_view(["POST"])
@permission_classes([AllowAny])
def get_draft_style_mmrs(request):
    serializer = DraftPredictMMRSerializer(data=request.data)

    if serializer.is_valid():
        draft_pk = serializer.validated_data["pk"]

    else:
        return Response(serializer.errors, status=400)

    try:
        draft = Draft.objects.get(pk=draft_pk)
    except Draft.DoesNotExist:
        return Response({"error": "Draft not found"}, status=404)
    cache_key = f"draft_sim_pk:{request.get_full_path()}"

    @cached_as(Draft, CustomUser, Tournament, Team, extra=cache_key, timeout=60 * 15)
    def get_data(request):
        return DraftSerializerMMRs(draft).data

    data = get_data(request)
    return Response(data, 201)


class UndoPickSerializer(serializers.Serializer):
    draft_pk = serializers.IntegerField(required=True)


@api_view(["POST"])
@permission_classes([IsStaff])
def undo_last_pick(request):
    """
    Undo the last pick in a draft.

    This removes the last draft round (if it has a choice) and restores
    the player to the available pool.

    Request body:
        draft_pk: int - Primary key of the draft

    Returns:
        200: Success with updated tournament data
        400: No picks to undo
        404: Draft not found
    """
    serializer = UndoPickSerializer(data=request.data)

    if serializer.is_valid():
        draft_pk = serializer.validated_data["draft_pk"]
    else:
        return Response(serializer.errors, status=400)

    try:
        draft = Draft.objects.get(pk=draft_pk)
    except Draft.DoesNotExist:
        return Response({"error": "Draft not found"}, status=404)

    # Find the last round with a choice
    last_round_with_choice = (
        draft.draft_rounds.filter(choice__isnull=False).order_by("-pick_number").first()
    )

    if not last_round_with_choice:
        return Response({"error": "No picks to undo"}, status=400)

    # Get the player that was picked
    player = last_round_with_choice.choice
    team = last_round_with_choice.team

    log.info(
        f"Undoing pick: {player.username} from team {team.name if team else 'unknown'}"
    )

    # Remove player from team
    if team and player:
        team.members.remove(player)
        team.save()

    # Note: users_remaining is a computed property, not a field.
    # Clearing the choice below will automatically make the player
    # appear in users_remaining again.

    # Clear the choice and reset the round
    last_round_with_choice.choice = None
    last_round_with_choice.save()

    # Clear the next round's captain so it gets recalculated on next pick
    next_round = (
        draft.draft_rounds.filter(pick_number__gt=last_round_with_choice.pick_number)
        .order_by("pick_number")
        .first()
    )
    if next_round and next_round.choice is None:
        next_round.captain = None
        next_round.was_tie = False
        next_round.tie_roll_data = None
        next_round.save()

    # Note: latest_round is a computed property that automatically returns
    # the first round without a choice. No need to set it manually.

    # Create pick_undone event
    undone_event = DraftEvent.objects.create(
        draft=draft,
        event_type="pick_undone",
        actor=request.user,
        payload={
            "pick_number": last_round_with_choice.pick_number,
            "undone_player_id": player.pk,
            "undone_player_name": player.username,
            "team_id": team.pk if team else None,
            "team_name": team.name if team else None,
        },
    )
    broadcast_event(undone_event)

    tournament = draft.tournament

    # Invalidate specific objects
    invalidate_obj(tournament)
    invalidate_obj(draft)

    return Response(TournamentSerializer(tournament).data, status=200)
