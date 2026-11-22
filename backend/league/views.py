"""League API viewset."""

from typing import Any

from cacheops import cached_as
from django.db.models import Count, Q, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from app.models import CustomUser, Game, League, Tournament
from app.serializers import LeagueMatchSerializer, LeaguesSerializer
from league.models import LeagueUser
from league.permissions import (
    IsLeagueAdmin,
    can_view_league_members,
    can_view_league_members_from_payload,
)
from league.serializers import LeagueSerializer, LeagueUserSerializer
from org.membership import member_access
from org.models import Organization
from org.permissions import has_org_staff_access
from user.models import BaseUserProfile, DotaUserProfile
from user.querysets import with_user_profiles


class LeagueView(viewsets.ModelViewSet):
    """League CRUD endpoints with org filtering."""

    queryset = League.objects.all()

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "list":
            return LeaguesSerializer
        return LeagueSerializer

    def get_queryset(self) -> QuerySet[League]:
        queryset = (
            League.objects.select_related("organization")
            .prefetch_related("admins", "staff")
            .annotate(
                tournament_count=Count("tournaments", distinct=True),
                users_count=Count("members", distinct=True),  # LeagueUser memberships
            )
            .order_by("name")
        )

        org_id = self.request.query_params.get("organization")
        if org_id:
            queryset = queryset.filter(organization__pk=org_id)
        return queryset

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "create":
            self.permission_classes = [IsAuthenticated]
        elif self.action in ["update", "partial_update", "destroy"]:
            self.permission_classes = [IsLeagueAdmin]
        else:
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Legacy `organization` key: the serializer ignores it (read-only), so
        # the authoritative org check on `organization_id` is in perform_create.
        org_id = request.data.get("organization")
        if org_id:
            try:
                org = Organization.objects.get(pk=org_id)
                if not has_org_staff_access(request.user, org):
                    return Response(
                        {"detail": "Must be organization staff to create league"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Organization.DoesNotExist:
                return Response(
                    {"detail": f"Organization {org_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Also check organization_ids if provided (for backwards compatibility)
        org_ids = request.data.get("organization_ids", [])
        for org_id in org_ids:
            try:
                org = Organization.objects.get(pk=org_id)
                if not has_org_staff_access(request.user, org):
                    return Response(
                        {"detail": "Must be organization staff to create league"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Organization.DoesNotExist:
                return Response(
                    {"detail": f"Organization {org_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer) -> None:
        org = serializer.validated_data.get("organization")
        if org is not None and not has_org_staff_access(self.request.user, org):
            raise PermissionDenied("Must be organization staff to create league")
        serializer.save()

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"league_list:{request.get_full_path()}"

        @cached_as(League, Tournament, Organization, extra=cache_key, timeout=60 * 10)
        def get_data() -> Any:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        pk = kwargs.get("pk")
        cache_key = f"league_detail:{pk}"

        @cached_as(League, Tournament, Organization, extra=cache_key, timeout=60 * 10)
        def get_data() -> Any:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(
            {
                **data,
                **member_access(
                    request.user,
                    can_view_league_members_from_payload(request.user, data),
                ),
            }
        )

    @action(detail=True, methods=["get"])
    def matches(self, request: Request, pk: str | None = None) -> Response:
        """Get all matches for this league (direct or via tournaments)."""
        league = self.get_object()
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

        tournament_pk = request.query_params.get("tournament")
        if tournament_pk:
            games = games.filter(tournament_id=tournament_pk)

        linked_only = request.query_params.get("linked_only")
        if linked_only == "true":
            games = games.filter(gameid__isnull=False)

        serializer = LeagueMatchSerializer(games, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def users(self, request: Request, pk: str | None = None) -> Response:
        """Get all users who are members of this league (via LeagueUser)."""
        league = get_object_or_404(League, pk=pk)
        if not can_view_league_members(request.user, league):
            raise PermissionDenied("You do not have access to this league's members.")
        cache_key = f"league_users:{pk}"

        @cached_as(
            LeagueUser,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data() -> Any:
            league_users = with_user_profiles(
                LeagueUser.objects.filter(league=league), "user", dota=True
            ).select_related("org_user")
            serializer = LeagueUserSerializer(league_users, many=True)
            return serializer.data

        data = get_data()
        return Response(data)
