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
    steam_account_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = (
            "nickname",
            "positions",
            "steam_account_id",
        )


class ProfileUpdateSerializer(serializers.Serializer):

    positions = PositionsSerializer(many=False, required=False)
    nickname = serializers.CharField(required=False, allow_blank=True, max_length=100)
    steam_account_id = serializers.IntegerField(required=False, allow_null=True)


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
        steam_account_id = serializer.validated_data.get("steam_account_id", None)
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
    if steam_account_id is not None:
        # steam_account_id is the 32-bit Friend ID (from Dotabuff URL)
        # save() auto-computes the 64-bit steamid
        if steam_account_id != user.steam_account_id:
            conflict = (
                CustomUser.objects.filter(steam_account_id=steam_account_id)
                .exclude(pk=user.pk)
                .first()
            )
            if conflict:
                return Response(
                    {"error": "This Friend ID is already linked to another account"},
                    status=409,
                )
            user.steam_account_id = steam_account_id
    if nickname is not None:
        user.nickname = nickname
    log.debug(f"{positions}, {steam_account_id}, {nickname}")
    with transaction.atomic():
        posObj.save()
        user.save()

    return Response(UserSerializer(user).data, status=201)
