import json
import logging
from datetime import timedelta

import requests
from cacheops import cached_as
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
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

from backend import settings

from .decorators import render_to
from .models import CustomUser, Draft, DraftRound, Game, Team, Tournament
from .permissions import IsStaff
from .serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    TeamSerializer,
    TournamentSerializer,
    TournamentsSerializer,
    UserSerializer,
)

log = logging.getLogger(__name__)
from .utils.avatar_utils import refresh_user_avatar


def logout(request):
    """Logs out user"""
    auth_logout(request)
    return redirect("/")


@render_to("home.html")
def home(request):
    """Home view, displays login mechanism"""
    if request.user.is_authenticated:
        return redirect("done")
    return None


@login_required
@render_to("home.html")
def done(request):
    """Login complete view, displays user data"""
    return


@render_to("home.html")
def validation_sent(request):
    """Email validation sent confirmation page"""
    return {
        "validation_sent": True,
        "email": request.session.get("email_validation_address"),
    }


@render_to("home.html")
def require_email(request):
    """Email required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "email_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_country(request):
    """Country required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "country_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_city(request):
    """City required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "city_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@psa("social:complete")
def ajax_auth(request, backend):
    """AJAX authentication endpoint"""
    if isinstance(request.backend, BaseOAuth1):
        token = {
            "oauth_token": request.REQUEST.get("access_token"),
            "oauth_token_secret": request.REQUEST.get("access_token_secret"),
        }
    elif isinstance(request.backend, BaseOAuth2):
        token = request.REQUEST.get("access_token")
    else:
        raise HttpResponseBadRequest("Wrong backend type")
    user = request.backend.do_auth(token, ajax=True)
    login(request, user)
    data = {"id": user.id, "username": user.username}
    return HttpResponse(json.dumps(data), mimetype="application/json")


from django.contrib.auth.models import User
from django.db import transaction

from .models import CustomUser
from .serializers import UserSerializer


@permission_classes((IsStaff,))
class UserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = CustomUser.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"user_list:{request.get_full_path()}"

        @cached_as(
            CustomUser.objects.all(), keep_fresh=True, extra=cache_key, timeout=60 * 60
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        cache_key = f"user_detail:{pk}"

        @cached_as(
            CustomUser.objects.filter(pk=pk),
            keep_fresh=True,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(UserView, self).get_permissions()

    @permission_classes((IsAdminUser,))
    def delete(self, request, *args, **kwargs):
        try:
            user = self.get_object()
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CustomUser.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


@permission_classes((IsStaff,))
class TournamentView(viewsets.ModelViewSet):
    serializer_class = TournamentSerializer
    queryset = Tournament.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"tournament_list:{request.get_full_path()}"

        @cached_as(
            Tournament,
            Team,
            CustomUser,
            Draft,
            Game,
            DraftRound,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        cache_key = f"tournament_detail:{pk}"

        @cached_as(
            Tournament.objects.filter(pk=pk),
            Team,
            CustomUser,
            Game,
            Draft,
            DraftRound,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            log.debug("get_tournament: fetching data")
            instance = self.get_object()

            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(TournamentView, self).get_permissions()


@permission_classes((IsStaff,))
class TeamView(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    queryset = Team.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"team_list:{request.get_full_path()}"

        @cached_as(
            Team.objects.all(),
            CustomUser,
            Tournament,
            Game,
            Draft,
            DraftRound,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            log.debug("get_team: fetching data")
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        cache_key = f"team_detail:{pk}"

        @cached_as(
            Team.objects.filter(pk=pk),
            CustomUser,
            Tournament,
            Game,
            Draft,
            DraftRound,
            keep_fresh=True,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(TeamView, self).get_permissions()

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


@permission_classes((IsStaff,))
class DraftView(viewsets.ModelViewSet):
    serializer_class = DraftSerializer
    queryset = Draft.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"draft_list:{request.get_full_path()}"

        @cached_as(
            Draft.objects.all(),
            DraftRound,
            Team,
            Tournament,
            CustomUser,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        cache_key = f"draft_detail:{pk}"

        @cached_as(
            Draft.objects.filter(pk=pk),
            DraftRound,
            Team,
            Tournament,
            CustomUser,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(DraftView, self).get_permissions()


@permission_classes((IsStaff,))
class DraftRoundView(viewsets.ModelViewSet):
    serializer_class = DraftRoundSerializer
    queryset = DraftRound.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"draftround_list:{request.get_full_path()}"

        @cached_as(
            DraftRound.objects.all(),
            Team,
            Tournament,
            CustomUser,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        cache_key = f"draftround_detail:{pk}"

        @cached_as(
            DraftRound.objects.filter(pk=pk),
            Team,
            Tournament,
            CustomUser,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(DraftRoundView, self).get_permissions()


class UserCreateView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsStaff]


@api_view(["GET"])
@permission_classes((AllowAny,))
def current_user(request):

    user = request.user
    if request.user.is_authenticated:

        data = UserSerializer(user).data
        return Response(data, 201)

    else:
        return Response()


from django.core.cache import cache


class GameCreateView(generics.CreateAPIView):
    serializer_class = GameSerializer
    permission_classes = [IsStaff]


@permission_classes((IsStaff,))
class GameView(viewsets.ModelViewSet):
    serializer_class = GameSerializer
    queryset = Game.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"game_list:{request.get_full_path()}"

        @cached_as(
            Game.objects.all(),
            Team,
            Tournament,
            CustomUser,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        cache_key = f"game_detail:{pk}"

        @cached_as(
            Game.objects.filter(pk=pk),
            Team,
            Tournament,
            CustomUser,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(GameView, self).get_permissions()


class GameView(viewsets.ModelViewSet):
    serializer_class = GameSerializer
    queryset = Game.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]


# for tournaments page
@permission_classes((AllowAny,))
class TournamentsBasicView(viewsets.ModelViewSet):
    """Read-only cached view for basic tournament data"""

    serializer_class = TournamentsSerializer
    queryset = Tournament.objects.all()

    http_method_names = [
        "get",
    ]

    def list(self, request, *args, **kwargs):
        cache_key = f"tournaments_list:{request.get_full_path()}"

        @cached_as(
            Tournament.objects.all(),
            Team,
            CustomUser,
            Game,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)


class TeamCreateView(generics.CreateAPIView):
    serializer_class = TeamSerializer
    permission_classes = [IsStaff]

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()


class TournamentCreateView(generics.CreateAPIView):
    serializer_class = TournamentSerializer
    permission_classes = [IsStaff]


class DraftCreateView(generics.CreateAPIView):
    serializer_class = DraftSerializer
    permission_classes = [IsStaff]


class DraftRoundCreateView(generics.CreateAPIView):
    serializer_class = DraftRoundSerializer
    permission_classes = [IsStaff]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_avatar(request):
    """
    Refresh the current user's Discord avatar by fetching the latest from Discord API.
    """
    try:
        user = request.user
        if not user.discordId:
            return Response(
                {"error": "User does not have a Discord ID associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use force_refresh=True to always fetch from Discord
        result = refresh_user_avatar(user.id)

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "updated": result["updated"],
                    "avatar_url": result["avatar_url"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        return Response(
            {"error": f"Failed to refresh avatar: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def refresh_user_avatar_admin(request, user_id):
    """
    Admin endpoint to refresh any user's Discord avatar.
    """
    try:
        result = refresh_user_avatar(user_id)

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "updated": result["updated"],
                    "avatar_url": result["avatar_url"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        return Response(
            {"error": f"Failed to refresh avatar: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_all_avatars(request):
    """
    Refreshes the avatars for all users in the database.
    This is a public endpoint but is rate-limited to once per hour.
    """
    cache_key = "avatar_refresh_last_run"
    last_run = cache.get(cache_key)

    if last_run and (timezone.now() - last_run < timedelta(hours=1)):
        return Response(
            {"message": "Avatar refresh can only be run once per hour."},
            status=status.HTTP_200_OK,
        )

    updated_count = 0
    users = CustomUser.objects.all()
    for user in users:
        if user.check_and_update_avatar():
            updated_count += 1

    cache.set(cache_key, timezone.now(), timeout=3600)  # Cache for 1 hour

    return Response(
        {"message": f"Avatar refresh complete. {updated_count} avatars updated."},
        status=status.HTTP_200_OK,
    )
