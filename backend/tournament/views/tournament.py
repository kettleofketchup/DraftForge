from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from cacheops import cached_as
from django.db import transaction
from django.db.models import BooleanField, Case, Count, Q, QuerySet, Value, When
from rest_framework import generics, viewsets
from rest_framework.decorators import action, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Game, Team, Tournament
from app.permissions import IsStaff
from discordbot.models import DiscordTournamentLog
from draft.models import Draft, DraftRound
from draft.services.team import apply_draft_options
from events.models import Event
from events.signup_window import user_signups_open_tournament_ids
from league.models import League
from org.membership import viewer_member_organization_ids
from org.models import Organization, OrgUserGameMmr
from telemetry.logging import get_logger
from tournament import buckets
from tournament.buckets import (
    tournament_bucket_cutoff,
    upcoming_q,
    upcoming_rank,
    utc_day_start,
)
from tournament.listing import (
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
from tournament.permissions import (
    CanEditTournament,
    can_edit_tournament,
    check_tournament_league_change,
)
from tournament.serializers.tournament import (
    TournamentListSerializer,
    TournamentSerializer,
    TournamentsSerializer,
)
from tournament.serializers.users import build_users_dict
from user.models import BaseUserProfile, DotaUserProfile

log = get_logger(__name__)


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
            OrgUserGameMmr,
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
            data["_users"] = build_users_dict(instance)

            return data

        data = get_data()
        return Response(data)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def viewer(self, request: Request, pk: str | None = None) -> Response:
        """Per-viewer and uncached: the detail payload above is shared by everyone."""
        tournament = get_object_or_404(
            Tournament.objects.nocache().select_related("league"), pk=pk
        )
        return Response(
            {"can_edit_tournament": can_edit_tournament(request.user, tournament)}
        )

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
        self._now = buckets._now()
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


class TournamentCreateView(generics.CreateAPIView):
    serializer_class = TournamentSerializer
    permission_classes = [IsStaff]

    def perform_create(self, serializer: TournamentSerializer) -> None:
        opts = serializer.validated_data.pop("draft_options", None)
        with transaction.atomic():
            serializer.save()
            if opts is not None:
                apply_draft_options(serializer.instance, opts, actor=self.request.user)
