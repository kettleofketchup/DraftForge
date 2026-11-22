from typing import Any

from cacheops import cached_as
from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from app.models import CustomUser, Tournament
from app.serializers import OrganizationsSerializer
from league.models import League
from org.features import FeatureKey, active_features
from org.membership import member_access
from org.mmr import game_mmrs_prefetch
from org.models import Organization, OrgUser, OrgUserGameMmr
from org.permissions import (
    IsOrgAdmin,
    IsOrgOwner,
    can_view_org_members,
    can_view_org_members_from_payload,
    is_org_role_holder,
    org_admin_staff_from_payload,
)
from org.serializers import OrganizationSerializer, OrgUserSerializer
from org.standing import api as standing

# BaseUserProfile owns nickname/avatar; DotaUserProfile owns
# positions/dota-mmr. Every @cached_as site below that ships
# nickname/avatar/positions MUST list both as dependencies, otherwise PATCH
# /api/users/me/profile/base/ or /game/dota/ won't invalidate the cached
# response. See backend/user/tests/test_cacheops.py for the grep guardrail.
from user.models import BaseUserProfile, DotaUserProfile
from user.querysets import with_user_profiles


def _feature_access(
    user: CustomUser | AnonymousUser, data: Any, can_view: bool
) -> dict[str, Any]:
    """Active feature keys plus per-viewer flags; merged after the cache."""
    features = active_features(data["pk"])
    promotion = FeatureKey.PROMOTION.value in features
    contributions = FeatureKey.CONTRIBUTIONS.value in features
    is_admin, is_staff = org_admin_staff_from_payload(user, data)
    tracks = standing.tracks_payload(
        data["pk"],
        viewer=user,
        features=features,
        roles=standing.ViewerRoles.fixed(is_admin, is_staff, can_view),
    )
    conduct = next((t for t in tracks if t["key"] == "conduct"), None)
    return {
        "features": features,
        # Must match has_org_promoter_access (the require_promoter gate).
        "can_use_promotion": promotion
        and (is_staff or is_org_role_holder(user, data["pk"])),
        "can_manage_promotion_templates": promotion and is_staff,
        "can_manage_promoters": promotion and is_admin,
        "can_view_contributions": contributions,
        "can_view_contributors": contributions and can_view,
        "can_manage_contributions": contributions and is_admin,
        "can_view_conduct": conduct is not None and conduct["board_open"],
        "can_view_own_conduct": conduct is not None and conduct["can_view_own"],
        "can_view_conduct_details": conduct is not None and is_staff,
        "can_manage_conduct": conduct is not None and conduct["can_manage"],
        "standing_tracks": tracks,
    }


def _org_viewer_access(
    user: CustomUser | AnonymousUser, data: Any
) -> dict[str, list[str] | bool | int | None]:
    can_view = can_view_org_members_from_payload(user, data)
    return {
        **member_access(user, can_view),
        **_feature_access(user, data, can_view),
    }


class OrganizationView(viewsets.ModelViewSet):
    """Organization CRUD endpoints."""

    queryset = Organization.objects.all()

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "list":
            return OrganizationsSerializer
        return OrganizationSerializer

    def get_queryset(self) -> QuerySet[Organization]:
        """Annotate counts and prefetch M2M to avoid N+1 queries."""
        return (
            Organization.objects.prefetch_related("admins", "staff")
            .annotate(
                league_count=Count("leagues", distinct=True),
                tournament_count=Count("leagues__tournaments", distinct=True),
                users_count=Count("members", distinct=True),  # OrgUser memberships
            )
            .order_by("name")
        )

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "destroy":
            self.permission_classes = [IsOrgOwner]
        elif self.action == "create":
            self.permission_classes = [IsAuthenticated]
        elif self.action in ["update", "partial_update"]:
            self.permission_classes = [IsOrgAdmin]
        else:
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def perform_create(self, serializer: OrganizationSerializer) -> None:
        """Set creator as owner and admin of the new organization."""
        org = serializer.save(owner=self.request.user)
        org.admins.add(self.request.user)
        OrgUser.objects.get_or_create(user=self.request.user, organization=org)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            response.data.update(_org_viewer_access(request.user, response.data))
        return response

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"organization_list:{request.get_full_path()}"

        @cached_as(Organization, League, Tournament, extra=cache_key, timeout=60 * 10)
        def get_data() -> Any:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        pk = kwargs.get("pk")
        cache_key = f"organization_detail:{pk}"

        @cached_as(Organization, League, Tournament, extra=cache_key, timeout=60 * 10)
        def get_data() -> Any:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response({**data, **_org_viewer_access(request.user, data)})

    @action(detail=True, methods=["get"])
    def users(self, request: Request, pk: str | None = None) -> Response:
        """Get all users who are members of this organization (via OrgUser)."""
        org = get_object_or_404(Organization, pk=pk)
        if not can_view_org_members(request.user, org):
            raise PermissionDenied(
                "You do not have access to this organization's members."
            )
        cache_key = f"organization_users:{pk}"

        @cached_as(
            OrgUser,
            OrgUserGameMmr,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            Organization,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data() -> Any:
            org_users = with_user_profiles(
                OrgUser.objects.filter(organization=org),
                "user",
                dota=True,
                steam_verified_org=True,
            ).prefetch_related(game_mmrs_prefetch(fresh=False))
            serializer = OrgUserSerializer(
                org_users,
                many=True,
                context={"include_game_mmrs": True, "include_steam_verified_org": True},
            )
            return serializer.data

        data = get_data()
        return Response(data)
