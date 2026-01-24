import json
import logging
from datetime import timedelta

import requests
from cacheops import cached_as
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
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
from .models import (
    CustomUser,
    Draft,
    DraftRound,
    Game,
    League,
    Organization,
    Team,
    Tournament,
)
from .permissions import IsStaff
from .permissions_org import (
    CanEditTournament,
    CanManageGame,
    IsLeagueAdmin,
    IsLeagueStaff,
    IsOrgAdmin,
    can_edit_tournament,
    can_manage_game,
    has_league_admin_access,
    has_org_admin_access,
)
from .serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    LeagueMatchSerializer,
    LeagueSerializer,
    LeaguesSerializer,
    OrganizationSerializer,
    OrganizationsSerializer,
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
    queryset = CustomUser.objects.select_related("positions").all()
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

    def get_queryset(self):
        queryset = Tournament.objects.all().order_by("-date_played")
        org_id = self.request.query_params.get("organization")
        league_id = self.request.query_params.get("league")
        if org_id:
            queryset = queryset.filter(league__organization_id=org_id)
        if league_id:
            queryset = queryset.filter(league_id=league_id)
        return queryset

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

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        elif self.action in ["update", "partial_update", "destroy"]:
            # Use object-level permission check for league admin
            self.permission_classes = [CanEditTournament]
        else:
            # For create, require at least league admin on some league
            # This is checked in perform_create
            self.permission_classes = [IsAuthenticated]
        return super(TournamentView, self).get_permissions()

    def perform_create(self, serializer):
        """Check that user can create tournament in the specified league."""
        league_id = self.request.data.get("league")
        if league_id:
            try:
                league = League.objects.get(pk=league_id)
                if not has_league_admin_access(self.request.user, league):
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied(
                        "You do not have permission to create tournaments in this league."
                    )
            except League.DoesNotExist:
                pass
        serializer.save()


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

        # Add active drafts info
        active_drafts = []

        # Team drafts: user is captain with pending pick in in_progress tournament
        from app.models import DraftTeam, HeroDraft

        pending_team_round = (
            DraftRound.objects.filter(
                captain=user,
                choice__isnull=True,
                draft__tournament__state="in_progress",
            )
            .select_related("draft__tournament")
            .order_by("pick_number")
            .first()
        )

        if pending_team_round:
            active_drafts.append(
                {
                    "type": "team_draft",
                    "tournament_pk": pending_team_round.draft.tournament.pk,
                    "draft_state": pending_team_round.draft.tournament.state,
                }
            )

        # Hero drafts: user is captain of a DraftTeam in an active HeroDraft
        active_hero_states = [
            "waiting_for_captains",
            "rolling",
            "choosing",
            "drafting",
        ]
        hero_draft_teams = DraftTeam.objects.filter(
            tournament_team__captain=user,
            draft__state__in=active_hero_states,
        ).select_related("draft__game__tournament")

        for draft_team in hero_draft_teams:
            hero_draft = draft_team.draft
            active_drafts.append(
                {
                    "type": "hero_draft",
                    "tournament_pk": hero_draft.game.tournament.pk,
                    "game_pk": hero_draft.game.pk,
                    "herodraft_pk": hero_draft.pk,
                    "draft_state": hero_draft.state,
                }
            )

        data["active_drafts"] = active_drafts
        return Response(data, 201)

    else:
        return Response()


from django.core.cache import cache


class GameCreateView(generics.CreateAPIView):
    """Create a new game - requires league staff access."""

    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        """Check that user can create game in the specified tournament/league."""
        tournament_id = self.request.data.get("tournament")
        league_id = self.request.data.get("league")

        # Check tournament's league
        if tournament_id:
            try:
                tournament = Tournament.objects.get(pk=tournament_id)
                if tournament.league:
                    from .permissions_org import has_league_staff_access

                    if not has_league_staff_access(
                        self.request.user, tournament.league
                    ):
                        from rest_framework.exceptions import PermissionDenied

                        raise PermissionDenied(
                            "You do not have permission to create games in this tournament."
                        )
            except Tournament.DoesNotExist:
                pass
        # Check direct league reference
        elif league_id:
            try:
                league = League.objects.get(pk=league_id)
                from .permissions_org import has_league_staff_access

                if not has_league_staff_access(self.request.user, league):
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied(
                        "You do not have permission to create games in this league."
                    )
            except League.DoesNotExist:
                pass
        serializer.save()


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

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        elif self.action in ["update", "partial_update", "destroy"]:
            # Use object-level permission check for league staff
            self.permission_classes = [CanManageGame]
        else:
            # For create, require league staff access
            # This is checked in perform_create
            self.permission_classes = [IsAuthenticated]
        return super(GameView, self).get_permissions()

    def perform_create(self, serializer):
        """Check that user can create game in the specified tournament/league."""
        tournament_id = self.request.data.get("tournament")
        league_id = self.request.data.get("league")

        # Check tournament's league
        if tournament_id:
            try:
                tournament = Tournament.objects.get(pk=tournament_id)
                if tournament.league and not can_manage_game(
                    self.request.user,
                    type(
                        "Game",
                        (),
                        {"league": tournament.league, "tournament": tournament},
                    )(),
                ):
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied(
                        "You do not have permission to create games in this tournament."
                    )
            except Tournament.DoesNotExist:
                pass
        # Check direct league reference
        elif league_id:
            try:
                from .models import League

                league = League.objects.get(pk=league_id)
                from .permissions_org import has_league_staff_access

                if not has_league_staff_access(self.request.user, league):
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied(
                        "You do not have permission to create games in this league."
                    )
            except League.DoesNotExist:
                pass
        serializer.save()


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


class OrganizationView(viewsets.ModelViewSet):
    """Organization CRUD endpoints."""

    queryset = Organization.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return OrganizationsSerializer
        return OrganizationSerializer

    def get_queryset(self):
        """Annotate counts and prefetch M2M to avoid N+1 queries."""
        return (
            Organization.objects.prefetch_related("admins", "staff")
            .annotate(
                league_count=Count("leagues", distinct=True),
                tournament_count=Count("leagues__tournaments", distinct=True),
            )
            .order_by("name")
        )

    def get_permissions(self):
        if self.action in ["create", "destroy"]:
            self.permission_classes = [IsAdminUser]
        elif self.action in ["update", "partial_update"]:
            self.permission_classes = [IsOrgAdmin]
        else:
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        cache_key = f"organization_list:{request.get_full_path()}"

        @cached_as(Organization, League, Tournament, extra=cache_key, timeout=60 * 10)
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"organization_detail:{pk}"

        @cached_as(Organization, League, Tournament, extra=cache_key, timeout=60 * 10)
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)


class LeagueView(viewsets.ModelViewSet):
    """League CRUD endpoints with org filtering."""

    queryset = League.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return LeaguesSerializer
        return LeagueSerializer

    def get_queryset(self):
        """Optimize with select_related, prefetch_related, and annotations."""
        queryset = (
            League.objects.select_related("organization")
            .prefetch_related("admins", "staff")
            .annotate(
                tournament_count=Count("tournaments", distinct=True),
            )
            .order_by("name")
        )

        org_id = self.request.query_params.get("organization")
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        return queryset

    def get_permissions(self):
        if self.action == "create":
            self.permission_classes = [IsAuthenticated]
        elif self.action in ["update", "partial_update", "destroy"]:
            self.permission_classes = [IsLeagueAdmin]
        else:
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        org_id = request.data.get("organization")
        if org_id:
            try:
                org = Organization.objects.get(pk=org_id)
                if not has_org_admin_access(request.user, org):
                    return Response(
                        {"detail": "Must be organization admin to create league"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Organization.DoesNotExist:
                return Response(
                    {"detail": "Organization not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        cache_key = f"league_list:{request.get_full_path()}"

        @cached_as(League, Tournament, Organization, extra=cache_key, timeout=60 * 10)
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"league_detail:{pk}"

        @cached_as(League, Tournament, Organization, extra=cache_key, timeout=60 * 10)
        def get_data():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    @action(detail=True, methods=["get"])
    def matches(self, request, pk=None):
        """Get all matches for this league (direct or via tournaments)."""
        league = self.get_object()
        # Games directly belonging to league OR games in tournaments belonging to league
        games = (
            Game.objects.filter(Q(league=league) | Q(tournament__league=league))
            .select_related(
                "tournament",
                "league",
                "radiant_team",
                "radiant_team__captain",
                "dire_team",
                "dire_team__captain",
                "winning_team",
            )
            .order_by("-pk")
        )

        # Optional filtering
        tournament_pk = request.query_params.get("tournament")
        if tournament_pk:
            games = games.filter(tournament_id=tournament_pk)

        linked_only = request.query_params.get("linked_only")
        if linked_only == "true":
            games = games.filter(gameid__isnull=False)

        serializer = LeagueMatchSerializer(games, many=True)
        return Response(serializer.data)


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
    users = CustomUser.objects.select_related("positions").all()
    for user in users:
        if user.check_and_update_avatar():
            updated_count += 1

    cache.set(cache_key, timezone.now(), timeout=3600)  # Cache for 1 hour

    return Response(
        {"message": f"Avatar refresh complete. {updated_count} avatars updated."},
        status=status.HTTP_200_OK,
    )
