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

from app.models import CustomUser, Draft, DraftRound, Team, Tournament
from app.permissions import IsStaff
from app.serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    TeamSerializer,
    TournamentSerializer,
    UserSerializer,
)
from backend import settings


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
        draft = tournament.draft.all()
        for d in draft:
            d.delete()

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
    team.save()

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
        for draft in tournament.draft.all():
            draft.delete()
    except Draft.DoesNotExist:
        pass  # No draft to delete
    logging.debug(f"Creating draft for tournament {tournament.name}")
    draft = Draft.objects.create(tournament=tournament)
    draft.save()
    draft.build_rounds()
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

    try:
        draft = tournament.draft.first()
        if len(tournament.draft.all()) > 1:
            logging.debug(
                f"Multiple drafts found for tournament {tournament.name}, deleting all but the first"
            )
            tournament.draft.exclude(pk=draft.pk).delete()
            logging.debug("Draft Issues")
            draft.save()

        draft = tournament.draft.first()
        if not draft:
            draft = Draft.objects.create(tournament=tournament)
            draft.build_rounds()
            draft.save()

        if not draft.draft_rounds.exists():
            logging.debug("Draft rounds do not exist, building them now")
            draft.build_rounds()

        logging.debug(f"Draft already exists for tournament {tournament.name}")
    except Draft.DoesNotExist:
        logging.debug(f"Draft doesn't exist for {tournament.pk}, creating new one")
        draft = Draft.objects.create(tournament=tournament)
        draft.build_rounds()
        draft.save()

    if not draft.draft_rounds.exists():
        logging.debug("Draft rounds do not exist, building them now")
        draft.build_rounds()
    draft.rebuild_teams()
    tournament = Tournament.objects.get(pk=tournament_pk)
    return Response(TournamentSerializer(tournament).data, status=201)
