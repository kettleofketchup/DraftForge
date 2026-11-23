from __future__ import annotations

from typing import Any, ClassVar, Protocol

from cacheops import cached_as
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from app.cache_utils import invalidate_after_commit
from app.models import (
    CustomUser,
    Game,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.permissions import IsStaff
from draft.models import Draft, DraftRound
from org.feature_errors import not_permitted
from org.models import Organization, OrgUserGameMmr
from org.permissions import has_org_staff_access
from telemetry.logging import get_logger
from tournament.permissions import CanEditTeam, can_create_team, can_edit_tournament
from tournament.serializers.team import (
    ManagedTeamSerializer,
    TeamActionRequestSerializer,
    TeamDeputyRequestSerializer,
    TeamLogSerializer,
    TeamRenameRequestSerializer,
    TeamReplaceCaptainRequestSerializer,
    TeamSerializer,
    TeamSubInRequestSerializer,
    TeamUserActionRequestSerializer,
    build_team_mmr_maps,
)
from tournament.serializers.users import TEAM_MMR_MAPS, tournament_organization
from tournament.services.team_audit import (
    log_snapshot_fields,
    roster_snapshot,
    write_team_log,
)
from tournament.services.team_management import (
    TeamChange,
    add_standin,
    follow_captain,
    live_conflicts,
    mark_dropout,
    other_team_user_ids,
    remove_standin,
    rename,
    replace_captain,
    restore_member,
    roster_conflict_body,
    set_captain,
    set_deputy,
    sub_in,
)
from tournament.services.team_references import TeamUsage, team_references, team_usage
from tournament.services.team_signals import (
    change_from_log,
    owning_team_audit,
    send_roster_changed_on_commit,
)
from user.models import BaseUserProfile, DotaUserProfile
from user.querysets import with_user_profiles

log = get_logger(__name__)


TEAM_MANAGE_ACTIONS: frozenset[str] = frozenset(
    {
        "set_captain",
        "set_deputy",
        "dropout",
        "restore",
        "standins",
        "standins_remove",
        "sub_in",
        "replace_captain",
        "rename",
        "history",
        "usage",
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


def _team_in_use_detail(name: str, usage: list[TeamUsage]) -> str:
    parts = [
        f"{u['count']} {u['label'] if u['count'] == 1 else u['label_plural']}"
        for u in usage
    ]
    return f"{name} is still used by {', '.join(parts)} and cannot be deleted."


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
            OrgUserGameMmr,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data() -> Any:
            log.debug("team_list_cache_miss", system="api", subsystem="main")
            teams = list(
                self.filter_queryset(self.get_queryset())
                .select_related("tournament__league")
                .prefetch_related("members")
            )
            context = {
                **self.get_serializer_context(),
                TEAM_MMR_MAPS: build_team_mmr_maps(teams),
            }
            serializer = self.get_serializer(teams, many=True, context=context)
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
            OrgUserGameMmr,
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
        return Response({**data, **self._viewer_fields(request.user, pk)})

    def _viewer_fields(
        self, user: CustomUser | AnonymousUser, pk: str
    ) -> dict[str, Any]:
        """Per-viewer, uncached: the flag, plus picker scope for managers."""
        if not user.is_authenticated:
            return {"can_manage_team": False}
        team = (
            Team.objects.nocache().select_related("tournament__league").filter(pk=pk)
        ).first()
        if (
            team is None
            or team.tournament_id is None
            or not can_edit_tournament(user, team.tournament)
        ):
            return {"can_manage_team": False}
        return self._manager_fields(team)

    def _manager_fields(self, team: Team) -> dict[str, Any]:
        org = tournament_organization(team.tournament, fresh=True)
        return {
            "can_manage_team": True,
            "organization_pk": org.pk if org else None,
            "league_pk": team.tournament.league_id if team.tournament else None,
            "other_team_user_pks": sorted(other_team_user_ids(team)),
            "other_teams": self._other_teams(team),
        }

    def _other_teams(self, team: Team) -> list[dict[str, Any]]:
        teams = (
            Team.objects.nocache()
            .filter(tournament_id=team.tournament_id)
            .exclude(pk=team.pk)
            .prefetch_related("members", "dropin_members")
            .order_by(F("placement").asc(nulls_first=True), "name", "pk")
        )
        return [
            {
                "pk": other.pk,
                "name": other.name,
                "placement": other.placement,
                "member_pks": sorted(u.pk for u in other.members.all()),
                "dropin_pks": sorted(u.pk for u in other.dropin_members.all()),
            }
            for other in teams
        ]

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

    def perform_create(self, serializer: BaseSerializer) -> None:
        _check_can_create_team(self.request.user, serializer)
        serializer.save()

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
        return Response(
            {**self.get_serializer(team).data, **self._manager_fields(team)}
        )

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

    @action(detail=True, methods=["post"], url_path="replace-captain")
    def replace_captain(self, request: Request, pk: str | None = None) -> Response:
        return self._manage(
            request,
            TeamReplaceCaptainRequestSerializer,
            lambda team, data, **kw: replace_captain(
                team,
                data["user_id"],
                mark_outgoing_dropout=data["mark_outgoing_dropout"],
                **kw,
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
                # Non-staff get 403 either way, so the status doesn't reveal ids.
                if not request.user.is_staff:
                    raise not_permitted()
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

    @action(detail=True, methods=["get"])
    def usage(self, request: Request, pk: str | None = None) -> Response:
        """What a DELETE would refuse on, without deleting anything."""
        teams = Team.objects.nocache().select_related("tournament__league")
        team = get_object_or_404(teams, pk=pk)
        self.check_object_permissions(request, team)
        usage = team_usage([team])
        return Response(
            {
                "in_use": bool(usage),
                "detail": _team_in_use_detail(team.name, usage) if usage else None,
                "usage": usage,
            }
        )

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Legacy DELETE: refuses teams other rows still use, audits the rest."""
        instance = self.get_object()
        teams = Team.objects.nocache().select_related("tournament__league")
        with transaction.atomic(), owning_team_audit():
            team = get_object_or_404(teams.select_for_update(), pk=instance.pk)
            self.check_object_permissions(request, team)
            references = team_references([team])
            if references:
                log.warning(
                    "team_delete_refused",
                    system="tournament",
                    subsystem="teams",
                    team_id=team.pk,
                    tournament_id=team.tournament_id,
                    actor_id=request.user.pk,
                    references=references,
                )
                usage = team_usage([team])
                return Response(
                    {
                        "code": "team_in_use",
                        "detail": _team_in_use_detail(team.name, usage),
                        "usage": usage,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            before = roster_snapshot(team)
            row = write_team_log(
                team,
                snapshot=log_snapshot_fields(team),
                action=TeamLogAction.TEAM_DELETED,
                via=TeamLogVia.WEB,
                actor=request.user,
                details={"before": before},
            )
            user_ids = {
                *before["member_ids"],
                *before["dropin_ids"],
                *before["left_ids"],
                *(
                    pk
                    for pk in (before["captain_id"], before["deputy_captain_id"])
                    if pk is not None
                ),
            }
            to_invalidate: list[Any] = list(
                CustomUser.objects.nocache().filter(pk__in=user_ids)
            )
            if team.tournament is not None:
                to_invalidate.append(team.tournament)
            invalidate_after_commit(*to_invalidate)
            send_roster_changed_on_commit(change_from_log(row))
            team.delete()
        log.info(
            "team_deleted",
            system="tournament",
            subsystem="teams",
            team_id=instance.pk,
            tournament_id=team.tournament_id,
            actor_id=request.user.pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

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
            reopens = (
                team.placement is not None
                and "placement" in serializer.validated_data
                and serializer.validated_data["placement"] is None
            )
            conflicts = live_conflicts(team) if reopens else []
            if conflicts:
                log.warning(
                    "team_patch_blocked_roster_conflict",
                    system="tournament",
                    subsystem="teams",
                    team_id=team.pk,
                    tournament_id=team.tournament_id,
                    actor_id=request.user.pk,
                    user_ids=[u.pk for u in conflicts],
                )
                return Response(
                    roster_conflict_body(team, conflicts),
                    status=status.HTTP_409_CONFLICT,
                )
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


def _check_can_create_team(user: CustomUser, serializer: BaseSerializer) -> None:
    if not can_create_team(user, serializer.validated_data.get("tournament")):
        raise PermissionDenied("You do not have permission to create teams here.")


class TeamCreateView(generics.CreateAPIView):
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer: TeamSerializer) -> None:
        _check_can_create_team(self.request.user, serializer)
        serializer.save()
