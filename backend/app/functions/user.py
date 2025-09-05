# import json
# import logging

# import requests
# from django.contrib.auth import login
# from django.contrib.auth import logout as auth_logout
# from django.contrib.auth.decorators import login_required
# from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
# from django.shortcuts import redirect, render
# from rest_framework import generics, permissions, serializers, status, viewsets
# from rest_framework.decorators import api_view, permission_classes
# from rest_framework.generics import GenericAPIView
# from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.reverse import reverse
# from social_core.backends.oauth import BaseOAuth1, BaseOAuth2

# # Create your views here.
# from social_django.models import USER_MODEL  # fix: skip
# from social_django.models import AbstractUserSocialAuth, DjangoStorage
# from social_django.utils import load_strategy, psa

# from app.models import CustomUser, Draft, DraftRound, Team, Tournament
# from app.permissions import IsStaff
# from app.serializers import (
#     DraftRoundSerializer,
#     DraftSerializer,
#     GameSerializer,
#     TeamSerializer,
#     TournamentSerializer,
#     UserSerializer,
# )
# from backend import settings

# log = logging.getLogger(__name__)


# class PickPlayerForRound(serializers.Serializer):
#     positions = serializers.JSONField(required=True)


# @api_view(["update"])
# @permission_classes([IsStaff])
# def modify_positions(request):
#     user = request.user
#     if user.is_anonymous or not user.is_staff:
#         return Response({"error": "Unauthorized"}, status=401)

#     serializer = PickPlayerForRound(data=request.data)

#     if serializer.is_valid():
#         positions = serializer.validated_data["positions    "]

#     else:
#         return Response(serializer.errors, status=400)

#     try:
#         draft_round = DraftRound.objects.get(pk=draft_round_pk)
#     except DraftRound.DoesNotExist:
#         return Response({"error": "Draft round not found"}, status=404)
#     try:
#         user = CustomUser.objects.get(pk=user_pk)
#     except CustomUser.DoesNotExist:
#         return Response({"error": "User not found"}, status=404)
#     try:
#         draft_round.pick_player(user)
#     except Exception as e:
#         logging.error(
#             f"Error picking player for draft round {draft_round_pk}: {str(e)}"
#         )
#         return Response({"error": f"Failed to pick player. {str(e)}"}, status=500)
#     try:
#         tournament = draft_round.draft.tournament
#     except Tournament.DoesNotExist:
#         return Response({"error": "Tournament not found"}, status=404)

#     draft_round.draft.save()

#     return Response(TournamentSerializer(tournament).data, status=201)
