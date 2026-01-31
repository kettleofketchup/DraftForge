import json
import logging

import requests
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
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

from app.models import CustomUser, Draft, DraftRound, PositionsModel, Team, Tournament
from app.permissions import IsStaff
from app.serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    PositionsSerializer,
    TeamSerializer,
    TournamentSerializer,
    UserSerializer,
)
from backend import settings

log = logging.getLogger(__name__)


# This allows a user to update only for certain fields
class ProfileUserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(many=False, read_only=True)
    nickname = serializers.CharField(required=False, allow_blank=True, max_length=100)
    steamid = serializers.CharField(required=False, allow_blank=True, max_length=100)

    class Meta:
        model = CustomUser
        fields = (
            "nickname",
            "positions",
            "steamid",
        )


class ProfileUpdateSerializer(serializers.Serializer):

    positions = PositionsSerializer(many=False, required=False)
    nickname = serializers.CharField(required=False, allow_blank=True, max_length=100)
    steamid = serializers.CharField(required=False, allow_blank=True, max_length=100)


@api_view(["post"])
@permission_classes([IsAuthenticated])
def profile_update(request):
    user = request.user
    if user.is_anonymous or not user.is_authenticated:
        return Response({"error": "Unauthorized"}, status=401)

    serializer = ProfileUpdateSerializer(data=request.data)
    log.debug(request.data)
    if serializer.is_valid():
        positions = serializer.validated_data.get("positions", None)
        steamid = serializer.validated_data.get("steamid", None)
        nickname = serializer.validated_data.get("nickname", None)

    else:
        return Response(serializer.errors, status=400)
    log.debug(serializer.validated_data)

    try:
        posObj = PositionsModel.objects.get(pk=user.positions.pk)

    except PositionsModel.DoesNotExist:
        return Response({"error": "Positions not found"}, status=404)

    if positions is not None:
        # Update the existing position object's fields
        for field, value in positions.items():
            setattr(posObj, field, value)
        user.positions = posObj
    if steamid is not None:
        # Normalize Steam ID to 64-bit format
        # Steam uses two formats:
        # - 64-bit (Friend ID): e.g., 76561198012345678
        # - 32-bit (Account ID): e.g., 52079950
        # Convert 32-bit to 64-bit if needed
        try:
            steamid_int = int(steamid)
            STEAM_ID_64_BASE = 76561197960265728
            if steamid_int < STEAM_ID_64_BASE:
                # This is a 32-bit account ID, convert to 64-bit
                steamid_int = steamid_int + STEAM_ID_64_BASE
            user.steamid = steamid_int
        except (ValueError, TypeError):
            return Response({"error": "Invalid Steam ID format"}, status=400)
    if nickname is not None:
        user.nickname = nickname
    log.debug(f"{positions}, {steamid}, {nickname}")
    with transaction.atomic():
        posObj.save()
        user.save()

    return Response(UserSerializer(user).data, status=201)
