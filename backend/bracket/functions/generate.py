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
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

# Create your views here.
from social_django.models import USER_MODEL  # fix: skip
from social_django.utils import load_strategy, psa

from app.models import CustomUser, Draft, DraftRound, Team, Tournament
from app.permissions import IsStaff
from app.serializers import TournamentSerializer

log = logging.getLogger(__name__)
from bracket.models import BracketSlot, TournamentBracket


class CreateDoubleElminationSerializer(serializers.Serializer):
    tournament_pk = serializers.IntegerField(required=True)


@api_view(["POST"])
@permission_classes([IsStaff])
def gen_double_elim(request):
    serializer = CreateDoubleElminationSerializer(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]
    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.get(pk=tournament_pk)

    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

        # Create a new team and add the user as a member (or captain)
    try:
        brackets = tournament.brackets.all()
        for b in brackets:
            log.debug(f"Deleting previous bracket: {b}")
            b.delete()

    except TournamentBracket.DoesNotExist:
        pass  # No draft exists, continue

    bracket = TournamentBracket.objects.create(
        tournament=tournament,
    )
    bracket.generate_double_elimination_bracket()
    bracket.save()

    return Response(TournamentBracket(bracket).data, status=201)
