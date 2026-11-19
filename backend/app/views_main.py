from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, ClassVar, Protocol, cast

from cacheops import cached_as
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import transaction
from django.db.models import BooleanField, Case, Count, Q, QuerySet, Value, When
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import (
    AllowAny,
    BasePermission,
    IsAdminUser,
    IsAuthenticated,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from social_core.backends.oauth import BaseOAuth1, BaseOAuth2
from social_django.utils import load_strategy, psa

from app import tournament_buckets
from app.cache_utils import invalidate_after_commit
from app.functions.teamdraft import apply_draft_options
from app.services.team_audit import (
    log_snapshot_fields,
    roster_snapshot,
    write_team_log,
)
from app.services.team_management import (
    TeamChange,
    add_standin,
    follow_captain,
    mark_dropout,
    remove_standin,
    rename,
    restore_member,
    set_captain,
    set_deputy,
    sub_in,
)
from app.services.team_signals import (
    change_from_log,
    owning_team_audit,
    send_roster_changed_on_commit,
)
from app.tournament_buckets import (
    tournament_bucket_cutoff,
    upcoming_q,
    upcoming_rank,
    utc_day_start,
)
from app.tournament_list import (
    ArchiveCursor,
    TournamentListPagination,
    TournamentListParams,
    archive_after_q,
    build_cursor_envelope,
    build_page_envelope,
    parse_tournament_list_params,
    resolve_organizations,
    tournaments_list_cache_key,
)
from events.models import Event
from events.signup_window import user_signups_open_tournament_ids
from league.models import LeagueUser
from league.serializers import LeagueUserSerializer
from org.contributions.services import delete_user_entries
from org.feature_errors import not_permitted
from org.features import FeatureKey, active_features
from org.membership import member_organization_ids, viewer_member_organization_ids
from org.models import OrgUser
from org.promotion.services import release_earning_sends
from org.serializers import OrgUserSerializer
from telemetry.logging import get_logger

# BaseUserProfile owns nickname/avatar; DotaUserProfile owns
# positions/dota-mmr. Every @cached_as site below that ships
# nickname/avatar/positions MUST list both as dependencies, otherwise PATCH
# /api/users/me/profile/base/ or /game/dota/ won't invalidate the cached
# response. See backend/user/tests/test_cacheops.py for the grep guardrail.
from user.models import BaseUserProfile, DotaUserProfile
from user.querysets import with_user_profiles

from .decorators import render_to
from .models import (
    CustomUser,
    Draft,
    DraftRound,
    DraftTeam,
    Game,
    League,
    Organization,
    ProfileClaimRequest,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from .permissions import IsStaff
from .permissions_org import (
    CanEditDraft,
    CanEditDraftRound,
    CanEditTeam,
    CanEditTournament,
    CanManageGame,
    IsLeagueAdmin,
    IsOrgAdmin,
    IsOrgOwner,
    can_edit_tournament,
    can_manage_game,
    can_view_league_members,
    can_view_league_members_from_payload,
    can_view_org_members,
    can_view_org_members_from_payload,
    check_tournament_league_change,
    has_league_staff_access,
    has_org_staff_access,
    is_org_role_holder,
    org_admin_staff_from_payload,
)
from .serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    LeagueMatchSerializer,
    LeagueSerializer,
    LeaguesSerializer,
    ManagedTeamSerializer,
    OrganizationSerializer,
    OrganizationsSerializer,
    TeamActionRequestSerializer,
    TeamDeputyRequestSerializer,
    TeamLogSerializer,
    TeamRenameRequestSerializer,
    TeamSerializer,
    TeamSubInRequestSerializer,
    TeamUserActionRequestSerializer,
    TournamentListSerializer,
    TournamentSerializer,
    TournamentsSerializer,
    UserSerializer,
    _build_users_dict,
)
from .steam_accounts import steam_account_id_holder, steam_account_id_identity
from .user_cache import serialize_user_core
from .utils.avatar_utils import refresh_user_avatar

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


@psa("social:complete")
def ajax_auth(request: HttpRequest, backend: str) -> HttpResponse:
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
            delete_user_entries(instance, actor=self.request.user)
            instance.delete()

    @permission_classes((IsAdminUser,))
    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            user = self.get_object()
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CustomUser.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

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

    def get_queryset(self) -> QuerySet[Tournament]:
        queryset = Tournament.objects.all().order_by("-date_played")
        org_id = self.request.query_params.get("organization")
        league_id = self.request.query_params.get("league")
        if org_id:
            queryset = queryset.filter(league__organization__pk=org_id)
        if league_id:
            queryset = queryset.filter(league_id=league_id)
        return queryset.prefetch_related(
            "source_event",
            "source_event__event_repeater",
            "draft_options",
            "users",
            "users__base_profile__dota_user_profile__positions",
            "teams__members",
            "teams__members__base_profile__dota_user_profile__positions",
            "teams__captain",
            "teams__captain__base_profile__dota_user_profile__positions",
            "teams__deputy_captain",
            "teams__deputy_captain__base_profile__dota_user_profile__positions",
            "teams__dropin_members",
            "teams__dropin_members__base_profile__dota_user_profile__positions",
            "teams__left_members",
            "teams__left_members__base_profile__dota_user_profile__positions",
        )

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"tournament_list:{request.get_full_path()}"

        @cached_as(
            Tournament,
            Team,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            Draft,
            Game,
            DraftRound,
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
        cache_key = f"tournament_detail_v2:{pk}"

        @cached_as(
            Tournament.objects.filter(pk=pk),
            Team,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            Game,
            Draft,
            DraftRound,
            extra=cache_key,
            timeout=60 * 10,
            # Every draft event refetches this; a read that straddles a commit
            # must not cache the pre-commit payload for the full timeout.
            keep_fresh=True,
        )
        def get_data() -> Any:
            log.debug(
                "tournament_cache_miss",
                system="api",
                subsystem="main",
                tournament_id=pk,
            )
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            data = serializer.data

            # Deduplicated user dict for frontend entity cache
            data["_users"] = _build_users_dict(instance)

            return data

        data = get_data()
        return Response(data)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.partial_update(request, *args, **kwargs)

    def perform_update(self, serializer: TournamentSerializer) -> None:
        check_tournament_league_change(
            self.request.user,
            serializer.instance,
            serializer.validated_data.get("league", serializer.instance.league),
        )
        opts = serializer.validated_data.pop("draft_options", None)
        with transaction.atomic():
            serializer.save()
            if opts is not None:
                apply_draft_options(serializer.instance, opts, actor=self.request.user)

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "discord_logs":
            self.permission_classes = [CanEditTournament]
        elif self.request.method == "GET":
            self.permission_classes = [AllowAny]
        elif self.action in ["update", "partial_update", "destroy"]:
            self.permission_classes = [CanEditTournament]
        else:
            # For create, require at least league admin on some league
            # This is checked in perform_create
            self.permission_classes = [IsAuthenticated]
        return super(TournamentView, self).get_permissions()

    @action(
        detail=True,
        methods=["get"],
        url_path="discord-logs",
        permission_classes=[CanEditTournament],
    )
    def discord_logs(self, request: Request, pk: str | None = None) -> Response:
        from discordbot.models import DiscordTournamentLog

        tournament = self.get_object()
        logs = DiscordTournamentLog.objects.filter(tournament=tournament)
        data = [
            {
                "id": log.pk,
                "category": log.category,
                "notification_type": log.notification_type,
                "message": log.message,
                "recipient_count": log.recipient_count,
                "success": log.success,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
        return Response(data)

    def perform_create(self, serializer: TournamentSerializer) -> None:
        """Check that user can create tournament in the specified league."""
        check_tournament_league_change(
            self.request.user, None, serializer.validated_data.get("league")
        )
        opts = serializer.validated_data.pop("draft_options", None)
        with transaction.atomic():
            serializer.save()
            if opts is not None:
                apply_draft_options(serializer.instance, opts, actor=self.request.user)


TEAM_MANAGE_ACTIONS: frozenset[str] = frozenset(
    {
        "set_captain",
        "set_deputy",
        "dropout",
        "restore",
        "standins",
        "standins_remove",
        "sub_in",
        "rename",
        "history",
    }
)


class TeamServiceCall(Protocol):
    def __call__(
        self,
        team: Team,
        data: dict[str, Any],
        *,
        actor: CustomUser,
        via: TeamLogVia,
        reason: str,
        acknowledged_codes: list[str],
    ) -> TeamChange: ...


class TeamLogPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def _can_read_scope(
    user: CustomUser, tournament_id: int | None, organization_id: int | None
) -> bool:
    if tournament_id is not None:
        tournament = (
            Tournament.objects.nocache()
            .select_related("league")
            .filter(pk=tournament_id)
            .first()
        )
        if tournament is not None:
            return can_edit_tournament(user, tournament)
    if organization_id is not None:
        organization = Organization.objects.nocache().filter(pk=organization_id).first()
        if organization is not None:
            return has_org_staff_access(user, organization)
    return bool(user.is_superuser or user.is_staff)


def _scope_q(tournament_id: int | None, organization_id: int | None) -> Q:
    by_tournament = (
        Q(tournament_id__isnull=True)
        if tournament_id is None
        else Q(tournament_id=tournament_id)
    )
    by_org = (
        Q(organization_id__isnull=True)
        if organization_id is None
        else Q(organization_id=organization_id)
    )
    return by_tournament & by_org


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

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"team_list:{request.get_full_path()}"

        @cached_as(
            Team.objects.all(),
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            Tournament,
            Game,
            Draft,
            DraftRound,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data() -> Any:
            log.debug("team_list_cache_miss", system="api", subsystem="main")
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        pk = kwargs["pk"]
        cache_key = f"team_detail:{pk}"

        @cached_as(
            Team.objects.filter(pk=pk),
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            Tournament,
            Game,
            Draft,
            DraftRound,
            # No keep_fresh: team detail ships member nickname/avatar/positions;
            # keep_fresh would serve stale members after a profile edit, same as
            # the user list/detail blocks above.
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data() -> Any:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        data = get_data()
        return Response(
            {**data, "can_manage_team": self._can_manage_team(request.user, pk)}
        )

    def _can_manage_team(self, user: CustomUser | AnonymousUser, pk: str) -> bool:
        if not user.is_authenticated:
            return False
        team = (
            Team.objects.nocache().select_related("tournament__league").filter(pk=pk)
        ).first()
        return (
            team is not None
            and team.tournament_id is not None
            and can_edit_tournament(user, team.tournament)
        )

    def get_permissions(self) -> list[BasePermission]:
        if self.action in TEAM_MANAGE_ACTIONS | {
            "update",
            "partial_update",
            "destroy",
        }:
            self.permission_classes = [CanEditTeam]
        elif self.request.method == "GET":
            self.permission_classes = [AllowAny]
        else:
            self.permission_classes = [IsAuthenticated]
        return super(TeamView, self).get_permissions()

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "history":
            return TeamLogSerializer
        if self.action == "retrieve" or self.action in TEAM_MANAGE_ACTIONS:
            return ManagedTeamSerializer
        return TeamSerializer

    def permission_denied(
        self, request: Request, message: str | None = None, code: str | None = None
    ) -> None:
        if request.user.is_authenticated and self.action in TEAM_MANAGE_ACTIONS:
            raise not_permitted()
        super().permission_denied(request, message=message, code=code)

    def get_authenticate_header(self, request: Request) -> str | None:
        if self.action in TEAM_MANAGE_ACTIONS:
            return 'Session realm="api"'
        return super().get_authenticate_header(request)

    def _manage(
        self,
        request: Request,
        serializer_class: type[TeamActionRequestSerializer],
        call: TeamServiceCall,
    ) -> Response:
        teams = Team.objects.nocache().select_related("tournament__league")
        team = get_object_or_404(teams, pk=self.kwargs["pk"])
        self.check_object_permissions(request, team)
        body = serializer_class(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        with transaction.atomic():
            team = get_object_or_404(teams.select_for_update(), pk=team.pk)
            self.check_object_permissions(request, team)
            change = call(
                team,
                data,
                actor=request.user,
                via=TeamLogVia.WEB,
                reason=data["reason"],
                acknowledged_codes=data["acknowledged_codes"],
            )
        team = teams.get(pk=change.team.pk)
        return Response({**self.get_serializer(team).data, "can_manage_team": True})

    @action(detail=True, methods=["post"], url_path="set-captain")
    def set_captain(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamUserActionRequestSerializer,
            lambda team, data, **kw: set_captain(team, data["user_id"], **kw),
        )

    @action(detail=True, methods=["post"], url_path="set-deputy")
    def set_deputy(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamDeputyRequestSerializer,
            lambda team, data, **kw: set_deputy(team, data["user_id"], **kw),
        )

    @action(detail=True, methods=["post"])
    def rename(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamRenameRequestSerializer,
            lambda team, data, **kw: rename(team, data["name"], **kw),
        )

    @action(detail=True, methods=["post"])
    def dropout(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamUserActionRequestSerializer,
            lambda team, data, **kw: mark_dropout(team, data["user_id"], **kw),
        )

    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamUserActionRequestSerializer,
            lambda team, data, **kw: restore_member(team, data["user_id"], **kw),
        )

    @action(detail=True, methods=["post"])
    def standins(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamUserActionRequestSerializer,
            lambda team, data, **kw: add_standin(team, data["user_id"], **kw),
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="standins/remove",
        url_name="standins-remove",
    )
    def standins_remove(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamUserActionRequestSerializer,
            lambda team, data, **kw: remove_standin(team, data["user_id"], **kw),
        )

    @action(detail=True, methods=["post"], url_path="sub-in")
    def sub_in(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamSubInRequestSerializer,
            lambda team, data, **kw: sub_in(
                team, data["standin_id"], data["replacing_id"], **kw
            ),
        )

    @action(detail=True, methods=["get"], pagination_class=TeamLogPagination)
    def history(self, request: Request, pk: str | None = None) -> Response:
        try:
            team_pk = int(pk or "")
        except ValueError:
            raise Http404 from None
        rows = TeamLog.objects.filter(team_snapshot_id=team_pk, event_team__isnull=True)
        scopes: set[tuple[int | None, int | None]] = set(
            rows.values_list("tournament_id", "organization_id").distinct()
        )
        team = (
            Team.objects.nocache()
            .select_related("tournament__league")
            .filter(pk=team_pk)
            .first()
        )
        if team is None:
            if not scopes:
                raise Http404
            log.debug(
                "team_history_orphan_access",
                system="tournament",
                subsystem="teams",
                team_id=team_pk,
            )
        else:
            snapshot = log_snapshot_fields(team)
            scopes.add((snapshot["tournament_id"], snapshot["organization_id"]))
        readable = [scope for scope in scopes if _can_read_scope(request.user, *scope)]
        if not readable:
            raise not_permitted()
        visible = Q()
        for scope in readable:
            visible |= _scope_q(*scope)
        queryset = with_user_profiles(
            with_user_profiles(rows.filter(visible), "actor", dota=True),
            "target_user",
            dota=True,
        ).order_by("-created_at", "-pk")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.partial_update(request, *args, **kwargs)

    # Serializer source name -> roster_snapshot key, for rows on a deleted team.
    _SNAPSHOT_KEYS: ClassVar[dict[str, str]] = {
        "name": "name",
        "captain": "captain_id",
        "deputy_captain": "deputy_captain_id",
        "members": "member_ids",
        "dropin_members": "dropin_ids",
        "left_members": "left_ids",
    }

    def _requested_snapshot(self, data: dict[str, Any]) -> dict[str, Any]:
        requested: dict[str, Any] = {}
        for name, key in self._SNAPSHOT_KEYS.items():
            if name not in data:
                continue
            value = data[name]
            if key.endswith("_ids"):
                requested[key] = sorted(user.pk for user in value)
            elif key.endswith("_id"):
                requested[key] = getattr(value, "pk", None)
            else:
                requested[key] = value
        return requested

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Legacy PATCH/PUT: audited, follows captain changes, 204 if the team is gone."""
        partial = kwargs.pop("partial", False)
        with transaction.atomic(), owning_team_audit():
            team = (
                Team.objects.nocache()
                .select_for_update()
                .select_related("tournament__league")
                .get(pk=self.get_object().pk)
            )
            before = roster_snapshot(team)
            snapshot = log_snapshot_fields(team)
            old_captain = team.captain
            tournament = team.tournament

            serializer = self.get_serializer(team, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            deleted = serializer.instance.pk is None
            extras: dict[str, Any] = {}
            after: dict[str, Any] | None = None
            moved_to: Tournament | None = None
            if deleted:
                team = None
                requested = self._requested_snapshot(serializer.validated_data)
                fields_changed = sorted(
                    k for k, v in requested.items() if before[k] != v
                )
            else:
                team = (
                    Team.objects.nocache()
                    .select_related("tournament__league")
                    .get(pk=team.pk)
                )
                if team.captain_id != before["captain_id"] and team.captain is not None:
                    extras = follow_captain(
                        team, old_captain, team.captain, actor=request.user
                    )
                after = roster_snapshot(team)
                fields_changed = sorted(k for k in before if before[k] != after[k])
                if team.tournament_id != snapshot["tournament_id"]:
                    fields_changed.append("tournament_id")
                    extras["before_tournament_id"] = snapshot["tournament_id"]
                    moved_to = team.tournament
                snapshot = log_snapshot_fields(team)

            if fields_changed:
                team_log = write_team_log(
                    team,
                    snapshot=snapshot,
                    action=TeamLogAction.LEGACY_PATCH,
                    via=TeamLogVia.WEB,
                    actor=request.user,
                    details={
                        "before": before,
                        "after": after,
                        "fields_changed": fields_changed,
                        **({"team_deleted": True} if deleted else {}),
                        **extras,
                    },
                )
                send_roster_changed_on_commit(change_from_log(team_log))
                user_ids = {
                    *before["member_ids"],
                    *before["dropin_ids"],
                    *before["left_ids"],
                    *((after or {}).get("member_ids") or []),
                    *((after or {}).get("dropin_ids") or []),
                    *((after or {}).get("left_ids") or []),
                }
                to_invalidate: list[Any] = list(
                    CustomUser.objects.nocache().filter(pk__in=user_ids)
                )
                if team is not None:
                    to_invalidate.append(team)
                if tournament is not None:
                    to_invalidate.append(tournament)
                if moved_to is not None:
                    to_invalidate.append(moved_to)
                invalidate_after_commit(*to_invalidate)

        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(team).data)


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
            data["_users"] = _build_users_dict(instance.tournament)

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


# for tournaments page
@permission_classes((AllowAny,))
class TournamentsBasicView(viewsets.ModelViewSet):
    """Read-only cached view for basic tournament data"""

    serializer_class = TournamentsSerializer
    queryset = Tournament.objects.all()

    http_method_names = [
        "get",
    ]

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        cache_key = f"tournaments_list:{request.get_full_path()}"

        @cached_as(
            Tournament.objects.all(),
            Team,
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            Game,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data() -> Any:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        data = get_data()
        return Response(data)


@permission_classes((AllowAny,))
class TournamentListView(viewsets.ReadOnlyModelViewSet):
    """Lightweight view for the tournament list page.

    Filters: organization, organizations (ids or ``mine``), open_signups,
    league, bucket (upcoming|archived), search. ``open_signups=1`` adds tournaments
    whose source event takes user signups to the organization scope.
    Paginates only when ``page`` or ``cursor`` is present (requires ``bucket``).
    Archived pages link onward with a keyset ``cursor`` on (date_played, pk).
    """

    serializer_class = TournamentListSerializer
    pagination_class = TournamentListPagination

    _now: datetime
    _cutoff: datetime
    _today_start: datetime
    _params: TournamentListParams

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        self._now = tournament_buckets._now()
        self._cutoff = tournament_bucket_cutoff(self._now)
        self._today_start = utc_day_start(self._now)
        self._params = resolve_organizations(
            parse_tournament_list_params(request.query_params),
            lambda: viewer_member_organization_ids(request.user),
        )

    def get_queryset(self) -> QuerySet[Tournament]:
        params = self._params
        qs = Tournament.objects.select_related(
            "league", "league__organization"
        ).annotate(user_count=Count("users", distinct=True))

        open_ids = user_signups_open_tournament_ids()
        qs = qs.annotate(
            signups_open=Case(
                When(pk__in=open_ids, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
            if open_ids
            else Value(False, output_field=BooleanField())
        )

        scope: Q | None = None
        if params.organization is not None:
            scope = Q(league__organization__id=params.organization)
        elif params.organizations is not None:
            scope = Q(league__organization__id__in=params.organizations)
        if params.open_signups:
            open_scope = Q(pk__in=open_ids)
            scope = open_scope if scope is None else scope | open_scope
        if scope is not None:
            qs = qs.filter(scope)
        if params.league is not None:
            qs = qs.filter(league_id=params.league)
        if params.search is not None:
            qs = qs.filter(
                Q(name__icontains=params.search)
                | Q(league__organization__name__icontains=params.search)
                | Q(league__name__icontains=params.search)
            )

        if params.bucket == "upcoming":
            return (
                qs.filter(upcoming_q(self._cutoff))
                .annotate(bucket_rank=upcoming_rank(self._today_start))
                .order_by("bucket_rank", "date_played", "pk")
            )
        if params.bucket == "archived":
            return qs.exclude(upcoming_q(self._cutoff)).order_by("-date_played", "-pk")
        return qs.order_by("-date_played")

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        params = self._params
        archived = params.bucket == "archived"

        def compute() -> Any:
            # cacheops' own queryset cache ignores select_related tables, so it
            # would serve stale org/league fields; cached_as below owns caching.
            queryset = self.filter_queryset(self.get_queryset()).nocache()
            if not params.paginated:
                return list(self.get_serializer(queryset, many=True).data)
            if params.cursor is None:
                rows = list(
                    self.paginator.paginate_queryset(queryset, request, view=self)
                )
                count = self.paginator.page.paginator.count
                has_next = self.paginator.page.has_next()
            else:
                count = queryset.count()
                rows = list(
                    queryset.filter(archive_after_q(params.cursor))[
                        : params.page_size + 1
                    ]
                )
                has_next = len(rows) > params.page_size
                rows = rows[: params.page_size]
            next_cursor = (
                ArchiveCursor(rows[-1].date_played, rows[-1].pk).token
                if archived and has_next and rows
                else None
            )
            return {
                "count": count,
                "next_cursor": next_cursor,
                "results": list(self.get_serializer(rows, many=True).data),
            }

        if params.search is not None:
            data = compute()
        else:
            data = cached_as(
                Tournament.objects.all(),
                League.objects.all(),
                Organization.objects.all(),
                Event.objects.all(),
                extra=tournaments_list_cache_key(params, self._cutoff),
                timeout=60 * 10,
            )(compute)()

        if not params.paginated:
            return Response(data)
        if archived:
            return Response(
                build_cursor_envelope(
                    request,
                    count=data["count"],
                    next_cursor=data["next_cursor"],
                    results=data["results"],
                )
            )
        return Response(
            build_page_envelope(
                request,
                count=data["count"],
                page=cast(int, params.page),
                page_size=params.page_size,
                results=data["results"],
            )
        )


def _member_access(
    user: CustomUser | AnonymousUser, can_view: bool
) -> dict[str, bool | int | None]:
    """Per-viewer member-list flag plus the viewer it was computed for."""
    return {
        "can_view_members": can_view,
        "members_viewer_pk": user.pk if user.is_authenticated else None,
    }


def _feature_access(
    user: CustomUser | AnonymousUser, data: Any, can_view: bool
) -> dict[str, list[str] | bool]:
    """Active feature keys plus per-viewer flags; merged after the cache."""
    features = active_features(data["pk"])
    promotion = FeatureKey.PROMOTION.value in features
    contributions = FeatureKey.CONTRIBUTIONS.value in features
    is_admin, is_staff = org_admin_staff_from_payload(user, data)
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
    }


def _org_viewer_access(
    user: CustomUser | AnonymousUser, data: Any
) -> dict[str, list[str] | bool | int | None]:
    can_view = can_view_org_members_from_payload(user, data)
    return {
        **_member_access(user, can_view),
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
            CustomUser,
            BaseUserProfile,
            DotaUserProfile,
            extra=cache_key,
            timeout=60 * 10,
        )
        def get_data() -> Any:
            org_users = with_user_profiles(
                OrgUser.objects.filter(organization=org), "user", dota=True
            )
            serializer = OrgUserSerializer(org_users, many=True)
            return serializer.data

        data = get_data()
        return Response(data)


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
                **_member_access(
                    request.user,
                    can_view_league_members_from_payload(request.user, data),
                ),
            }
        )

    @action(detail=True, methods=["get"])
    def matches(self, request: Request, pk: str | None = None) -> Response:
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


class TeamCreateView(generics.CreateAPIView):
    serializer_class = TeamSerializer
    permission_classes = [IsStaff]

    @transaction.atomic
    def perform_create(self, serializer: TeamSerializer) -> None:
        serializer.save()


class TournamentCreateView(generics.CreateAPIView):
    serializer_class = TournamentSerializer
    permission_classes = [IsStaff]

    def perform_create(self, serializer: TournamentSerializer) -> None:
        opts = serializer.validated_data.pop("draft_options", None)
        with transaction.atomic():
            serializer.save()
            if opts is not None:
                apply_draft_options(serializer.instance, opts, actor=self.request.user)


class DraftCreateView(generics.CreateAPIView):
    serializer_class = DraftSerializer
    permission_classes = [IsStaff]


class DraftRoundCreateView(generics.CreateAPIView):
    serializer_class = DraftRoundSerializer
    permission_classes = [IsStaff]


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
    org) and updates avatars in bulk. See `app.tasks.avatar_refresh
    .refresh_avatars_batched`.

    Rate-limited to once per hour.
    """
    cache_key = "avatar_refresh_last_run"
    last_run = cache.get(cache_key)

    if last_run and (timezone.now() - last_run < timedelta(hours=1)):
        return Response(
            {"message": "Avatar refresh can only be run once per hour."},
            status=status.HTTP_200_OK,
        )

    # Set the cache key BEFORE dispatch so a second caller arriving during
    # task execution short-circuits instead of queueing another task.
    cache.set(cache_key, timezone.now(), timeout=3600)

    from app.tasks.avatar_refresh import refresh_avatars_batched

    refresh_avatars_batched.delay()

    return Response(
        {"message": "Avatar refresh queued."},
        status=status.HTTP_202_ACCEPTED,
    )
