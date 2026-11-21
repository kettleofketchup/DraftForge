"""Team draft REST viewsets and create views (routers stay in backend/urls.py)."""

from __future__ import annotations

from typing import Any

from cacheops import cached_as
from rest_framework import generics, viewsets
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Team, Tournament
from app.permissions import IsStaff
from app.permissions_tournament import CanEditTournament
from app.serializers import build_users_dict
from draft.models import Draft, DraftRound
from draft.permissions import CanEditDraft, CanEditDraftRound
from draft.serializers.team import DraftRoundSerializer, DraftSerializer
from user.models import BaseUserProfile, DotaUserProfile


@permission_classes((IsAuthenticated,))
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

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"draft_list:{request.get_full_path()}"

        @cached_as(
            Draft.objects.all(),
            DraftRound,
            Team,
            Tournament,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data() -> Any:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        pk = kwargs["pk"]
        cache_key = f"draft_detail:{pk}"

        @cached_as(
            Draft.objects.filter(pk=pk),
            DraftRound,
            Team,
            Tournament,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data() -> Any:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            data = serializer.data

            # Deduplicated user dict for frontend entity cache
            data["_users"] = build_users_dict(instance.tournament)

            return data

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
            self.permission_classes = [CanEditDraft]
        else:
            self.permission_classes = [IsAuthenticated]
        return super(DraftView, self).get_permissions()


@permission_classes((IsAuthenticated,))
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

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"draftround_list:{request.get_full_path()}"

        @cached_as(
            DraftRound.objects.all(),
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
        cache_key = f"draftround_detail:{pk}"

        @cached_as(
            DraftRound.objects.filter(pk=pk),
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
            self.permission_classes = [CanEditDraftRound]
        else:
            self.permission_classes = [IsAuthenticated]
        return super(DraftRoundView, self).get_permissions()


class DraftCreateView(generics.CreateAPIView):
    serializer_class = DraftSerializer
    permission_classes = [IsStaff]


class DraftRoundCreateView(generics.CreateAPIView):
    serializer_class = DraftRoundSerializer
    permission_classes = [IsStaff]
