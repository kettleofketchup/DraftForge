"""Team-draft pick and undo endpoints."""

from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.broadcast import broadcast_event
from app.cache_utils import invalidate_after_commit
from app.functions.shuffle_draft import assign_next_shuffle_captain
from app.functions.teamdraft import (
    activate_round,
    advance_after_pick,
    record_pick_timing,
)
from app.functions.tournament import _serialize_tournament
from app.models import (
    CustomUser,
    Draft,
    DraftEvent,
    DraftOptions,
    DraftRound,
    Team,
    TeamDraftState,
    Tournament,
)
from app.permissions_org import can_edit_tournament
from app.tasks.draft_tick import evaluate_client_pick_time
from app.tasks.teamdraft_tick import start_team_tick_broadcaster_after_commit
from telemetry.logging import get_logger

log = get_logger(__name__)

_NOT_ACCEPTING_PICKS_STATES: frozenset[str] = frozenset(
    {TeamDraftState.PENDING, TeamDraftState.RESUMING, TeamDraftState.COMPLETED}
)


class PickPlayerForRound(serializers.Serializer):
    draft_round_pk = serializers.IntegerField(required=True)
    user_pk = serializers.IntegerField(required=True)
    client_picked_at = serializers.DateTimeField(required=False, allow_null=True)


class UndoPickSerializer(serializers.Serializer):
    draft_pk = serializers.IntegerField(required=True)


def _not_active_round(active: DraftRound | None) -> Response:
    return Response(
        {
            "code": "not_active_round",
            "active_pick_number": active.pick_number if active else None,
        },
        status=409,
    )


def _authorize_pick(
    user: CustomUser, draft_round: DraftRound
) -> tuple[bool, Response | None]:
    """Return (is_tournament_staff, rejection) for a pick on this round."""
    is_tournament_staff = False
    if draft_round.draft and draft_round.draft.tournament:
        is_tournament_staff = can_edit_tournament(user, draft_round.draft.tournament)
    if is_tournament_staff or draft_round.captain == user:
        return is_tournament_staff, None

    log.warning(
        "pick_unauthorized",
        system="tournament",
        subsystem="draft",
        user_id=user.pk,
        username=user.username,
        draft_round_id=draft_round.pk,
        captain_username=draft_round.captain.username,
    )
    return is_tournament_staff, Response(
        {"error": "Only tournament staff or the captain for this round can make picks"},
        status=403,
    )


def _reject_pick(
    draft: Draft,
    draft_round: DraftRound,
    active: DraftRound | None,
    timed: bool,
    is_tournament_staff: bool,
) -> Response | None:
    if timed:
        if draft.state in _NOT_ACCEPTING_PICKS_STATES:
            return Response(
                {"code": "draft_not_accepting_picks", "state": draft.state},
                status=409,
            )
        if draft.state == TeamDraftState.PAUSED and not is_tournament_staff:
            return Response({"code": "paused_staff_only"}, status=403)
        if active is None or draft_round.pk != active.pk:
            return _not_active_round(active)
    if draft_round.choice_id is not None:
        return Response({"code": "already_picked"}, status=409)
    return None


def _should_activate_next(draft: Draft, active: DraftRound | None, timed: bool) -> bool:
    if not timed:
        return False
    if draft.state == TeamDraftState.PAUSED:
        return True
    return (
        draft.state == TeamDraftState.DRAFTING
        and active is not None
        and active.started_at is not None
    )


def _effective_pick_time(
    draft: Draft, now: datetime, client_picked_at: datetime | None
) -> datetime:
    effective, _source, _age = evaluate_client_pick_time(
        now, client_picked_at, draft.pk, system="teamdraft", subsystem="timer"
    )
    if draft.state == TeamDraftState.PAUSED and draft.paused_at is not None:
        effective = min(effective, draft.paused_at)
    return effective


def _record_picked_event(
    draft: Draft, draft_round: DraftRound, picked: CustomUser, actor: CustomUser
) -> None:
    captain = draft_round.captain
    round_team = draft_round.team
    picked_event = DraftEvent.objects.create(
        draft=draft,
        event_type="player_picked",
        actor=actor,
        payload={
            "pick_number": draft_round.pick_number,
            "captain_id": captain.pk,
            "captain_name": captain.username,
            "captain_avatar_url": captain.avatarUrl,
            "picked_id": picked.pk,
            "picked_name": picked.username,
            "picked_avatar_url": picked.avatarUrl,
            "team_id": round_team.pk if round_team else None,
            "team_name": round_team.name if round_team else None,
        },
    )
    transaction.on_commit(lambda e=picked_event: broadcast_event(e))


def _pick_under_lock(
    actor: CustomUser,
    draft_id: int,
    draft_round_pk: int,
    picked: CustomUser,
    client_picked_at: datetime | None,
    is_tournament_staff: bool,
) -> Response | tuple[Tournament, dict | None]:
    """Apply a pick inside the caller's transaction; a Response means rejected."""
    draft = Draft.objects.select_for_update().get(pk=draft_id)
    active = draft.lock_active_round()
    draft_round = DraftRound.objects.select_for_update().get(pk=draft_round_pk)
    # Shuffle timeout skip keeps the round pk but swaps its captain.
    if not (is_tournament_staff or draft_round.captain_id == actor.pk):
        log.info(
            "pick_captain_changed",
            system="tournament",
            subsystem="draft",
            user_id=actor.pk,
            draft_round_id=draft_round.pk,
            captain_id=draft_round.captain_id,
        )
        return _not_active_round(active)

    team = (
        Team.objects.select_for_update()
        .filter(tournament=draft.tournament_id, captain_id=draft_round.captain_id)
        .first()
    )
    tournament = draft.tournament
    options = tournament.get_draft_options(fresh=True)
    timed = options.timer_enabled

    rejection = _reject_pick(draft, draft_round, active, timed, is_tournament_staff)
    if rejection is not None:
        return rejection

    activate_next = _should_activate_next(draft, active, timed)
    now = timezone.now()
    effective = _effective_pick_time(draft, now, client_picked_at)

    draft_round.pick_player(picked)
    if timed and draft_round.started_at and team is not None:
        record_pick_timing(
            draft_round,
            team,
            completed_at=now,
            effective_pick_time=effective,
            default_reserve_ms=options.reserve_time_ms,
        )
    _record_picked_event(draft, draft_round, picked, actor)

    tie_data = None
    if draft.draft_style == "shuffle" and draft.users_remaining.exists():
        tie_data = assign_next_shuffle_captain(draft)

    advance_after_pick(draft, options, now=now, activate=activate_next)
    invalidate_after_commit(tournament, draft)
    return tournament, tie_data


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pick_player_for_round(request: Request) -> Response:
    """
    Pick a player for a draft round.

    Authorization: Staff can pick for any round. Captains can only pick
    for their own round (when they are the captain for that round).

    Request body:
        draft_round_pk: int - Primary key of the draft round
        user_pk: int - Primary key of the user to pick
        client_picked_at: optional ISO datetime of the client-side pick

    Returns:
        201: Success with updated tournament data
        400: Validation error
        403: Not authorized (not staff and not captain for this round)
        404: Draft round or user not found
        409: Draft not accepting picks / not the active round / already picked
        500: Error during pick
    """
    serializer = PickPlayerForRound(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    draft_round_pk = serializer.validated_data["draft_round_pk"]
    user_pk = serializer.validated_data["user_pk"]
    client_picked_at = serializer.validated_data.get("client_picked_at")

    try:
        draft_round = DraftRound.objects.select_related("draft__tournament").get(
            pk=draft_round_pk
        )
    except DraftRound.DoesNotExist:
        return Response({"error": "Draft round not found"}, status=404)

    is_tournament_staff, denied = _authorize_pick(request.user, draft_round)
    if denied is not None:
        return denied

    try:
        user = CustomUser.objects.get(pk=user_pk)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    try:
        with transaction.atomic():
            result = _pick_under_lock(
                request.user,
                draft_round.draft_id,
                draft_round.pk,
                user,
                client_picked_at,
                is_tournament_staff,
            )
    except Exception as e:
        log.error(
            "pick_failed",
            system="tournament",
            subsystem="draft",
            draft_round_id=draft_round_pk,
            error=str(e),
        )
        return Response({"error": f"Failed to pick player. {str(e)}"}, status=500)

    if isinstance(result, Response):
        return result
    tournament, tie_data = result
    response_data = _serialize_tournament(tournament)
    if tie_data:
        response_data["tie_resolution"] = tie_data
    return Response(response_data, status=201)


def _restore_undone_round_clock(
    draft: Draft,
    last_round: DraftRound,
    options: DraftOptions,
    had_completed_at: bool,
) -> None:
    """Re-arm the undone round's clock for timed drafts, or clear it."""
    timed_undo = options.timer_enabled and had_completed_at
    if timed_undo and draft.state in (
        TeamDraftState.DRAFTING,
        TeamDraftState.RESUMING,
    ):
        last_round.save()
        now = (
            draft.resuming_until
            if draft.state == TeamDraftState.RESUMING
            else timezone.now()
        )
        activate_round(draft, last_round, options, now=now, armed=True)
        start_team_tick_broadcaster_after_commit(draft.pk)
    elif timed_undo and draft.state == TeamDraftState.PAUSED:
        last_round.save()
        activate_round(draft, last_round, options, now=timezone.now(), armed=False)
    else:
        last_round.started_at = None
        last_round.timed_out_at = None
        last_round.save()


def _reset_next_shuffle_round(draft: Draft, undone_pick_number: int) -> None:
    next_round = (
        draft.draft_rounds.select_for_update()
        .filter(pick_number__gt=undone_pick_number, choice__isnull=True)
        .order_by("pick_number")
        .first()
    )
    if next_round is not None:
        next_round.captain = None
        next_round.was_tie = False
        next_round.tie_roll_data = None
        next_round.save()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def undo_last_pick(request: Request) -> Response:
    """
    Undo the last pick in a draft.

    Requires tournament staff access.
    This removes the last draft round (if it has a choice) and restores
    the player to the available pool.

    Request body:
        draft_pk: int - Primary key of the draft

    Returns:
        200: Success with updated tournament data
        400: No picks to undo
        403: Not authorized
        404: Draft not found
    """
    serializer = UndoPickSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    draft_pk = serializer.validated_data["draft_pk"]

    try:
        draft = Draft.objects.select_related("tournament").get(pk=draft_pk)
    except Draft.DoesNotExist:
        return Response({"error": "Draft not found"}, status=404)

    if not draft.tournament or not can_edit_tournament(request.user, draft.tournament):
        return Response(
            {"error": "You do not have permission to undo picks in this draft"},
            status=403,
        )

    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(pk=draft_pk)
        tournament = draft.tournament
        options = tournament.get_draft_options(fresh=True)

        if options.timer_enabled and draft.state == TeamDraftState.PENDING:
            return Response({"code": "no_picks_to_undo"}, status=409)

        prev_active = draft.lock_active_round()
        last_round = (
            draft.draft_rounds.select_for_update()
            .filter(choice__isnull=False)
            .order_by("-pick_number")
            .first()
        )
        if last_round is None:
            return Response({"error": "No picks to undo"}, status=400)

        player = last_round.choice
        team = last_round.team

        log.info(
            "pick_undone",
            system="tournament",
            subsystem="draft",
            draft_id=draft.pk,
            player_id=player.pk,
            player_username=player.username,
            team_id=team.pk if team else None,
            team_name=team.name if team else None,
        )

        if team and player:
            team.members.remove(player)
            team.save()

        had_completed_at = last_round.completed_at is not None
        last_round.choice = None
        last_round.completed_at = None

        if draft.state == TeamDraftState.COMPLETED:
            draft.state = TeamDraftState.DRAFTING
            draft.paused_at = None
            draft.resuming_until = None
            draft.is_manual_pause = False

        if prev_active is not None:
            prev_active.started_at = None
            prev_active.timed_out_at = None
            prev_active.save(update_fields=["started_at", "timed_out_at"])

        undone_event = DraftEvent.objects.create(
            draft=draft,
            event_type="pick_undone",
            actor=request.user,
            payload={
                "pick_number": last_round.pick_number,
                "undone_player_id": player.pk,
                "undone_player_name": player.username,
                "team_id": team.pk if team else None,
                "team_name": team.name if team else None,
            },
        )
        transaction.on_commit(lambda e=undone_event: broadcast_event(e))

        _restore_undone_round_clock(draft, last_round, options, had_completed_at)
        if draft.draft_style == "shuffle":
            _reset_next_shuffle_round(draft, last_round.pick_number)

        draft.save()
        invalidate_after_commit(tournament, draft)

    return Response(_serialize_tournament(tournament), status=200)
