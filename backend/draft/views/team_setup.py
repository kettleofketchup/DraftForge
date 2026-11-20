"""Team draft setup endpoints: init, rebuild and draft-style MMR prediction."""

from cacheops import cached_as
from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit
from app.functions.tournament import _serialize_tournament
from app.models import CustomUser, Team, TeamLog, TeamLogVia, Tournament
from app.permissions_org import can_edit_tournament
from draft.models import Draft
from draft.serializers.team import DraftPredictMMRSerializer, DraftSerializerMMRs
from draft.services.team_reset import (
    NoEligibleCaptains,
    TeamsReferenced,
    reset_draft_teams,
)
from events.discord.tournament_dispatch import notify_draft_started
from telemetry.logging import get_logger
from user.models import BaseUserProfile, DotaUserProfile

log = get_logger(__name__)


class CreateDraftRounds(serializers.Serializer):
    tournament_pk = serializers.IntegerField(required=True)
    draft_style = serializers.ChoiceField(
        choices=["snake", "normal", "shuffle"],
        required=False,
        default=None,
    )
    force = serializers.BooleanField(required=False, default=False)


def _get_or_create_draft(tournament: Tournament) -> Draft:
    try:
        return Draft.objects.get(tournament=tournament)
    except Draft.DoesNotExist:
        log.debug(
            "draft_created",
            system="tournament",
            subsystem="draft",
            tournament_id=tournament.pk,
        )
        return Draft.objects.create(tournament=tournament)


def _notify_draft_started_after_commit(tournament: Tournament, draft: Draft) -> None:
    if tournament.discord_send_draft_link:
        transaction.on_commit(lambda: notify_draft_started(tournament, draft))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_draft_rounds(request: Request) -> Response:
    """Start or restart a team draft. Requires tournament staff access."""
    serializer = CreateDraftRounds(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]
    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.select_related(
            "league", "league__organization"
        ).get(pk=tournament_pk)
    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)

    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission to generate draft rounds"},
            status=403,
        )

    force = serializer.validated_data["force"]
    log.debug(
        "draft_initializing",
        system="tournament",
        subsystem="draft",
        tournament_id=tournament.pk,
    )

    with transaction.atomic():
        tournament = (
            Tournament.objects.select_for_update().nocache().get(pk=tournament_pk)
        )
        try:
            report = reset_draft_teams(tournament, force=force)
        except NoEligibleCaptains:
            return Response(
                {
                    "error": "Cannot initialize draft: no captains assigned. Assign captains to teams first."
                },
                status=400,
            )
        except TeamsReferenced as refused:
            return Response(
                {
                    "error": str(refused),
                    "code": "draft_reset_has_references",
                    "references": refused.references,
                    "usage": refused.usage,
                },
                status=409,
            )

        draft = _get_or_create_draft(tournament)
        draft_style = serializer.validated_data.get("draft_style")
        if draft_style:
            draft.draft_style = draft_style

        invalidate_after_commit(tournament, draft, *report.reset_teams)
        draft.build_rounds()
        draft.save()
        _notify_draft_started_after_commit(tournament, draft)

    log.info(
        "draft_reset_completed",
        system="tournament",
        subsystem="draft",
        tournament_id=tournament.pk,
        reset_count=len(report.reset_teams),
        removed_count=len(report.removed_users),
        dropped_count=len(report.dropped_teams),
        kept_count=len(report.kept_teams),
        forced=force,
    )
    data = _serialize_tournament(tournament)
    data["draft_reset"] = report.as_dict()
    return Response(data, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_team(request: Request) -> Response:
    """Rebuild teams in a tournament. Requires tournament staff access."""
    serializer = CreateDraftRounds(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]
    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.select_related(
            "league", "league__organization"
        ).get(pk=tournament_pk)
    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)

    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission to rebuild teams"},
            status=403,
        )

    with transaction.atomic():
        tournament = (
            Tournament.objects.select_for_update().nocache().get(pk=tournament_pk)
        )
        if not tournament.captains:
            return Response(
                {
                    "error": "Cannot rebuild teams: no captains assigned. Assign captains to teams first."
                },
                status=400,
            )
        draft = _get_or_create_draft(tournament)
        invalidate_after_commit(tournament, draft)

        # rebuild_teams runs before build_rounds so team MMR counts captains only.
        will_build_rounds = not draft.draft_rounds.exists()
        if (
            not will_build_rounds
            and TeamLog.objects.nocache()
            .filter(team__tournament=tournament)
            .exclude(via=TeamLogVia.SYSTEM)
            .exists()
        ):
            log.info(
                "draft_rebuild_refused",
                system="tournament",
                subsystem="draft",
                tournament_id=tournament.pk,
                draft_id=draft.pk,
                reason="team_changes_logged",
            )
            return Response(
                {
                    "code": "team_changes_logged",
                    "error": "Staff have changed these teams; rebuilding them "
                    "from the draft picks would undo those changes.",
                },
                status=409,
            )
        draft.rebuild_teams(clear_only=will_build_rounds)

        if will_build_rounds:
            log.debug(
                "draft_rounds_building",
                system="tournament",
                subsystem="draft",
                tournament_id=tournament.pk,
                draft_id=draft.pk,
            )
            draft.build_rounds()
            _notify_draft_started_after_commit(tournament, draft)
        else:
            log.debug(
                "draft_rounds_exist",
                system="tournament",
                subsystem="draft",
                tournament_id=tournament.pk,
                draft_id=draft.pk,
            )
        draft.save()

    log.debug(
        "tournament_rebuilt",
        system="tournament",
        subsystem="draft",
        tournament_id=tournament.pk,
    )
    return Response(_serialize_tournament(tournament), status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def get_draft_style_mmrs(request: Request) -> Response:
    serializer = DraftPredictMMRSerializer(data=request.data)

    if serializer.is_valid():
        draft_pk = serializer.validated_data["pk"]

    else:
        return Response(serializer.errors, status=400)

    try:
        draft = Draft.objects.get(pk=draft_pk)
    except Draft.DoesNotExist:
        return Response({"error": "Draft not found"}, status=404)
    cache_key = f"draft_sim_pk:{request.get_full_path()}"

    # cached_as on CustomUser must also list BaseUserProfile/DotaUserProfile (user/tests/test_cacheops.py)
    @cached_as(
        Draft,
        CustomUser,
        BaseUserProfile,
        DotaUserProfile,
        Tournament,
        Team,
        extra=cache_key,
        timeout=60 * 15,
    )
    def get_data(request: Request) -> dict:
        return DraftSerializerMMRs(draft).data

    data = get_data(request)
    return Response(data, 201)
