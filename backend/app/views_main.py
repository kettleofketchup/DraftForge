from __future__ import annotations

from typing import Any

from cacheops import cached_as
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    BasePermission,
    IsAdminUser,
    IsAuthenticated,
)
from rest_framework.request import Request
from rest_framework.response import Response
from social_django.utils import load_strategy

from draft.models import DraftRound, DraftTeam
from league.models import League
from org.membership import member_organization_ids
from org.models import Organization, OrgUser
from org.permissions import has_org_staff_access
from org.promotion.services import release_earning_sends
from org.standing import api as standing
from telemetry.logging import get_logger
from tournament.models import Game, Tournament
from user.avatar import refresh_user_avatar

# BaseUserProfile owns nickname/avatar; DotaUserProfile owns
# positions/dota-mmr. Every @cached_as site below that ships
# nickname/avatar/positions MUST list both as dependencies, otherwise PATCH
# /api/users/me/profile/base/ or /game/dota/ won't invalidate the cached
# response. See backend/user/tests/test_cacheops.py for the grep guardrail.
from user.models import BaseUserProfile, DotaUserProfile
from user.querysets import with_user_profiles
from user.steam_accounts import steam_account_id_holder, steam_account_id_identity
from user.tasks.avatar_refresh import refresh_avatars_batched

from .decorators import render_to
from .models import CustomUser, ProfileClaimRequest
from .permissions import IsStaff
from .serializers import UserSerializer
from .user_cache import serialize_user_core

log = get_logger(__name__)


def logout(request: HttpRequest) -> HttpResponseRedirect:
    auth_logout(request)
    return redirect("/")


@render_to("home.html")
def home(request: HttpRequest) -> HttpResponseRedirect | None:
    """Home view, displays login mechanism"""
    if request.user.is_authenticated:
        return redirect("done")
    return None


@login_required
@render_to("home.html")
def done(request: HttpRequest) -> None:
    """Login complete view, displays user data"""
    return


@render_to("home.html")
def validation_sent(request: HttpRequest) -> dict[str, Any]:
    return {
        "validation_sent": True,
        "email": request.session.get("email_validation_address"),
    }


@render_to("home.html")
def require_email(request: HttpRequest) -> dict[str, Any]:
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "email_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_country(request: HttpRequest) -> dict[str, Any]:
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "country_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_city(request: HttpRequest) -> dict[str, Any]:
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "city_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@permission_classes((IsStaff,))
class UserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    # Prefetch the M2M reverse relations that UserSerializer exposes as
    # role-membership lists. Without these the four SerializerMethodFields
    # on the list endpoint fire 4·N extra queries on a cold cacheops key.
    # base_profile is required because nickname/avatar resolve via the
    # @property on CustomUser, which reads self.base_profile.*.
    queryset = (
        with_user_profiles(CustomUser.objects.all(), dota=True)
        .prefetch_related(
            "owned_organizations",
            "admin_organizations",
            "staff_organizations",
            "admin_leagues",
            "staff_leagues",
        )
        .all()
    )
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
        cache_key = f"user_list:{request.get_full_path()}"

        @cached_as(
            CustomUser.objects.all(),
            BaseUserProfile,
            DotaUserProfile,
            # No keep_fresh: it defeats predictable eviction after a profile
            # edit, so nickname/avatar/positions edits would serve stale until
            # TTL. Strict eviction is correct for user payloads.
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
        cache_key = f"user_detail:{pk}"

        @cached_as(
            CustomUser.objects.filter(pk=pk),
            BaseUserProfile,
            DotaUserProfile,
            # No keep_fresh: its deferred eviction served a stale nickname/avatar
            # after a profile edit. This is the `/api/users/<pk>/` payload the
            # profile header reads — strict eviction makes edits reflect without
            # a manual refresh.
            extra=cache_key,
            timeout=60 * 60,
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
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        elif self.request.method in ("PATCH", "PUT"):
            self.permission_classes = [IsAuthenticated]
        else:
            self.permission_classes = [IsStaff]
        return super(UserView, self).get_permissions()

    def check_object_permissions(self, request: Request, obj: CustomUser) -> None:
        """Allow org admins/staff to edit users in their organizations."""
        super().check_object_permissions(request, obj)
        if request.method in ("PATCH", "PUT") and not request.user.is_staff:
            target_orgs = OrgUser.objects.filter(user=obj).select_related(
                "organization"
            )
            has_access = any(
                has_org_staff_access(request.user, ou.organization)
                for ou in target_orgs
            )
            if not has_access:
                self.permission_denied(request)

    def perform_destroy(self, instance: CustomUser) -> None:
        with transaction.atomic():
            release_earning_sends(instance)
            standing.on_user_deleted(instance, actor=self.request.user)
            instance.delete()

    @action(detail=True, methods=["post"])
    def claim(self, request: Request, pk: str | None = None) -> Response:
        """
        Request to claim a user profile.

        Use case: An org admin manually added a player with just their Steam ID.
        Later, that player logs in via Discord and wants to claim their profile.

        Requirements:
        - Current user must be authenticated (has Discord ID)
        - Target user must have a Steam ID (the profile to claim)
        - Target user must NOT have a Discord ID (not already claimed)
        - Target user must be a member of at least one organization
        - Current user must be different from target user

        Creates a ProfileClaimRequest that must be approved by an org admin.
        """
        current_user = request.user
        if not current_user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        target_user = self.get_object()

        if target_user.pk == current_user.pk:
            return Response(
                {"error": "Cannot claim your own profile"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Target must have Steam ID (the valuable data to claim)
        if not target_user.steamid:
            return Response(
                {"error": "Target profile has no Steam ID to claim"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Target must not have Discord ID (would mean it's already claimed/owned)
        if target_user.discordId:
            return Response(
                {
                    "error": "Cannot claim a profile that already has a Discord account linked"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_user.steamid and current_user.steamid != target_user.steamid:
            return Response(
                {"error": "Your account already has a different Steam ID linked"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org_membership = OrgUser.objects.filter(user=target_user).first()
        if not org_membership:
            return Response(
                {"error": "Target profile is not a member of any organization"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_request = ProfileClaimRequest.objects.filter(
            claimer=current_user,
            target_user=target_user,
            status=ProfileClaimRequest.Status.PENDING,
        ).first()

        if existing_request:
            return Response(
                {"error": "You already have a pending claim request for this profile"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        claim_request = ProfileClaimRequest.objects.create(
            claimer=current_user,
            target_user=target_user,
            organization=org_membership.organization,
            status=ProfileClaimRequest.Status.PENDING,
        )

        return Response(
            {
                "message": "Claim request submitted. An organization admin will review your request.",
                "request_id": claim_request.pk,
                "status": claim_request.status,
            },
            status=status.HTTP_201_CREATED,
        )


class UserCreateView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsStaff]


@api_view(["GET"])
@permission_classes((AllowAny,))
def current_user(request: Request) -> Response:
    user = request.user
    if request.user.is_authenticated:
        data = UserSerializer(user).data
        data["member_organization_ids"] = member_organization_ids(
            user,
            admin_org_ids=data["admin_organization_ids"],
            staff_org_ids=data["staff_organization_ids"],
        )

        active_drafts = []

        # Team drafts: user is captain with pending pick in in_progress tournament
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_users(request: Request) -> Response:
    """Fetch multiple users by pk for entity cache hydration.
    Returns core fields only — scoped data (MMR) comes from context-specific fetches.
    """
    pks = request.data.get("pks", [])
    if not isinstance(pks, list) or not all(isinstance(pk, int) for pk in pks):
        return Response({"error": "Provide a list of integer pks"}, status=400)
    if len(pks) == 0 or len(pks) > 200:
        return Response({"error": "Provide 1-200 pks"}, status=400)

    data = [d for d in (serialize_user_core(pk) for pk in pks) if d]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def steam_account_id_lookup(request: Request, steam_account_id: int) -> Response:
    """Who already holds this Friend ID? Returns {"holder": null} when free.

    Lets the edit-user form warn on blur instead of letting the save fail.
    """
    holder = steam_account_id_holder(steam_account_id)
    return Response({"holder": steam_account_id_identity(holder) if holder else None})


@api_view(["GET"])
@permission_classes([AllowAny])
def home_stats(request: Request) -> Response:
    """
    Cached endpoint for home page statistics.
    Returns counts only, much more efficient than fetching full objects.
    """
    cache_key = "home_stats"

    @cached_as(
        Tournament,
        Game,
        Organization,
        League,
        extra=cache_key,
        timeout=60 * 5,
    )
    def get_stats() -> dict[str, int]:
        return {
            "tournament_count": Tournament.objects.count(),
            "game_count": Game.objects.count(),
            "organization_count": Organization.objects.count(),
            "league_count": League.objects.count(),
        }

    return Response(get_stats())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_avatar(request: Request) -> Response:
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
def refresh_user_avatar_admin(request: Request, user_id: int) -> Response:
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
def refresh_all_avatars(request: Request) -> Response:
    """Queue an asynchronous avatar refresh.

    Returns immediately (202 Accepted) and dispatches a Celery task that
    fetches Discord guild members in batched calls (1–3 paginated calls per
    org) and updates avatars in bulk. See `user.tasks.avatar_refresh
    .refresh_avatars_batched`.

    Public on purpose: every users-list page view fires it, so avatars stay
    fresh for everyone. One shared cache key caps it at one task per hour no
    matter who calls or how often. `cache.add` is an atomic set-if-absent, so
    concurrent callers can't both win and double-queue the task.
    """
    if not cache.add("avatar_refresh_last_run", timezone.now(), timeout=3600):
        return Response(
            {"message": "Avatar refresh can only be run once per hour."},
            status=status.HTTP_200_OK,
        )

    refresh_avatars_batched.delay()

    return Response(
        {"message": "Avatar refresh queued."},
        status=status.HTTP_202_ACCEPTED,
    )
