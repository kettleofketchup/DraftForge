from __future__ import annotations

from typing import Any

from cacheops import cached_as
from rest_framework import generics, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Game, Team, Tournament
from league.models import League
from league.permissions import has_league_staff_access
from tournament.permissions import CanEditTournament, CanManageGame, can_manage_game
from tournament.serializers.game import GameSerializer
from user.models import BaseUserProfile, DotaUserProfile


class GameCreateView(generics.CreateAPIView):
    """Create a new game - requires league staff access."""

    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer: GameSerializer) -> None:
        """Check that user can create game in the specified tournament/league."""
        tournament_id = self.request.data.get("tournament")
        league_id = self.request.data.get("league")

        if tournament_id:
            try:
                tournament = Tournament.objects.get(pk=tournament_id)
                if tournament.league:
                    if not has_league_staff_access(
                        self.request.user, tournament.league
                    ):
                        raise PermissionDenied(
                            "You do not have permission to create games in this tournament."
                        )
            except Tournament.DoesNotExist:
                pass
        elif league_id:
            try:
                league = League.objects.get(pk=league_id)
                if not has_league_staff_access(self.request.user, league):
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

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"game_list:{request.get_full_path()}"

        @cached_as(
            Game.objects.all(),
            Team,
            Tournament,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data() -> Any:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        pk = kwargs["pk"]
        cache_key = f"game_detail:{pk}"

        @cached_as(
            Game.objects.filter(pk=pk),
            Team,
            Tournament,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data() -> Any:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(data)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "discord_logs":
            self.permission_classes = [CanEditTournament]
        elif self.request.method == "GET":
            self.permission_classes = [AllowAny]
        elif self.action in ["update", "partial_update", "destroy"]:
            self.permission_classes = [CanManageGame]
        else:
            # For create, require league staff access
            # This is checked in perform_create
            self.permission_classes = [IsAuthenticated]
        return super(GameView, self).get_permissions()

    def perform_create(self, serializer: GameSerializer) -> None:
        """Check that user can create game in the specified tournament/league."""
        tournament_id = self.request.data.get("tournament")
        league_id = self.request.data.get("league")

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
                    raise PermissionDenied(
                        "You do not have permission to create games in this tournament."
                    )
            except Tournament.DoesNotExist:
                pass
        elif league_id:
            try:
                league = League.objects.get(pk=league_id)
                if not has_league_staff_access(self.request.user, league):
                    raise PermissionDenied(
                        "You do not have permission to create games in this league."
                    )
            except League.DoesNotExist:
                pass
        serializer.save()
