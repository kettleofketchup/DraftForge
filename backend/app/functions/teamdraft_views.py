"""Team-draft timer HTTP endpoints: ready, start, pause, resume (spec §2)."""

from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit
from app.functions.teamdraft import (
    RESUME_COUNTDOWN_SECONDS,
    activate_round,
    emit_event,
    seed_missing_reserve_pools,
    start_draft,
    team_for_round,
    team_payload,
)
from app.functions.tournament import _serialize_tournament
from app.models import Draft, DraftRound, Team, TeamDraftState, Tournament
from app.permissions_org import can_edit_tournament
from app.tasks.teamdraft_tick import start_team_tick_broadcaster_after_commit
from telemetry.logging import get_logger

log = get_logger(__name__)


def _error(code: str, http_status: int, **extra: object) -> Response:
    return Response({"code": code, **extra}, status=http_status)


def _wrong_state(draft: Draft) -> Response:
    return _error("wrong_state", status.HTTP_400_BAD_REQUEST, state=draft.state)


def _ok(draft: Draft) -> Response:
    tournament = Tournament.objects.nocache().get(pk=draft.tournament_id)
    return Response(_serialize_tournament(tournament))


def _is_armed(draft: Draft, options, active: DraftRound | None) -> bool:
    return bool(
        options.timer_enabled
        and draft.state in (TeamDraftState.DRAFTING, TeamDraftState.RESUMING)
        and active is not None
        and active.started_at is not None
    )


def _log(event: str, draft: Draft, user_id: int) -> None:
    log.info(
        event,
        system="teamdraft",
        subsystem="view",
        draft_id=draft.pk,
        user_id=user_id,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teamdraft_set_ready(request: Request, draft_pk: int) -> Response:
    draft = get_object_or_404(Draft, pk=draft_pk)
    if not Team.objects.filter(
        tournament=draft.tournament, captain=request.user
    ).exists():
        return _error("not_captain", status.HTTP_403_FORBIDDEN)
    ready = bool(request.data.get("ready"))

    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=draft_pk)
        if draft.state != TeamDraftState.PENDING:
            return _wrong_state(draft)
        team = Team.objects.select_for_update().get(
            tournament=draft.tournament, captain=request.user
        )
        team.draft_is_ready = ready
        team.save(update_fields=["draft_is_ready"])
        invalidate_after_commit(draft.tournament)
        emit_event(
            draft,
            "captain_ready" if ready else "captain_unready",
            team_payload(team),
            actor=request.user,
        )
    _log("captain_ready_set", draft, request.user.pk)
    return _ok(draft)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teamdraft_start(request: Request, draft_pk: int) -> Response:
    draft = get_object_or_404(Draft, pk=draft_pk)
    if not can_edit_tournament(request.user, draft.tournament):
        return _error("forbidden", status.HTTP_403_FORBIDDEN)

    now = timezone.now()
    actor = {"actor_id": request.user.pk, "actor_name": request.user.username}
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=draft_pk)
        options = draft.tournament.get_draft_options(fresh=True)
        if not options.timer_enabled:
            return _error("timer_disabled", status.HTTP_400_BAD_REQUEST)
        active = draft.lock_active_round()

        if draft.state == TeamDraftState.PENDING:
            teams = list(
                Team.objects.select_related("captain").filter(
                    tournament=draft.tournament, captain__isnull=False
                )
            )
            not_ready = [
                {
                    "team_id": t.pk,
                    "team_name": t.name,
                    "captain_id": t.captain.pk,
                    "captain_name": t.captain.username,
                }
                for t in teams
                if not t.draft_is_ready
            ]
            start_draft(draft, options, now=now)
            if not_ready:
                emit_event(
                    draft,
                    "draft_force_started",
                    {**actor, "not_ready": not_ready},
                    actor=request.user,
                )
            else:
                emit_event(draft, "draft_started_by_staff", actor, actor=request.user)
            start_team_tick_broadcaster_after_commit(draft.pk)
        elif draft.state == TeamDraftState.DRAFTING and active is not None:
            if _is_armed(draft, options, active):
                return _error("already_armed", status.HTTP_409_CONFLICT)
            seed_missing_reserve_pools(draft, options)
            activate_round(draft, active, options, now=now, armed=True)
            start_team_tick_broadcaster_after_commit(draft.pk)
            emit_event(draft, "draft_started_by_staff", actor, actor=request.user)
        else:
            return _wrong_state(draft)
    _log("draft_started", draft, request.user.pk)
    return _ok(draft)


def _can_pause_or_resume(request: Request, draft: Draft) -> bool:
    return Team.objects.filter(
        tournament=draft.tournament, captain=request.user
    ).exists() or can_edit_tournament(request.user, draft.tournament)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teamdraft_pause(request: Request, draft_pk: int) -> Response:
    draft = get_object_or_404(Draft, pk=draft_pk)
    if not _can_pause_or_resume(request, draft):
        return _error("forbidden", status.HTTP_403_FORBIDDEN)

    now = timezone.now()
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=draft_pk)
        options = draft.tournament.get_draft_options(fresh=True)
        active = draft.lock_active_round()
        if draft.state != TeamDraftState.DRAFTING or not _is_armed(
            draft, options, active
        ):
            return _error("clock_not_running", status.HTTP_400_BAD_REQUEST)
        draft.state = TeamDraftState.PAUSED
        draft.paused_at = now
        draft.is_manual_pause = True
        draft.save(update_fields=["state", "paused_at", "is_manual_pause"])
        emit_event(
            draft,
            "draft_paused",
            {
                "reason": "manual",
                "paused_by_id": request.user.pk,
                "paused_by_name": request.user.username,
                **team_payload(team_for_round(draft, active)),
            },
            actor=request.user,
        )
    _log("draft_paused", draft, request.user.pk)
    return _ok(draft)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teamdraft_resume(request: Request, draft_pk: int) -> Response:
    draft = get_object_or_404(Draft, pk=draft_pk)
    if not _can_pause_or_resume(request, draft):
        return _error("forbidden", status.HTTP_403_FORBIDDEN)

    now = timezone.now()
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=draft_pk)
        options = draft.tournament.get_draft_options(fresh=True)
        if not options.timer_enabled or draft.state != TeamDraftState.PAUSED:
            return _error("clock_not_running", status.HTTP_400_BAD_REQUEST)
        rnd = draft.lock_active_round()
        if rnd is None:
            return _error("clock_not_running", status.HTTP_400_BAD_REQUEST)
        countdown = timedelta(seconds=RESUME_COUNTDOWN_SECONDS)
        resuming_until = now + countdown
        if rnd.started_at:
            rnd.started_at += (now - (draft.paused_at or now)) + countdown
        else:
            rnd.started_at = resuming_until
        if rnd.grace_time_ms is None:
            rnd.grace_time_ms = options.grace_time_ms
        rnd.save(update_fields=["started_at", "grace_time_ms"])
        draft.state = TeamDraftState.RESUMING
        draft.paused_at = None
        draft.resuming_until = resuming_until
        draft.is_manual_pause = False
        draft.save(
            update_fields=["state", "paused_at", "resuming_until", "is_manual_pause"]
        )
        emit_event(
            draft,
            "draft_resumed",
            {
                "resumed_by_id": request.user.pk,
                "resumed_by_name": request.user.username,
                "resuming_until": resuming_until.isoformat(),
            },
            actor=request.user,
        )
        start_team_tick_broadcaster_after_commit(draft.pk)
    _log("draft_resumed", draft, request.user.pk)
    return _ok(draft)
