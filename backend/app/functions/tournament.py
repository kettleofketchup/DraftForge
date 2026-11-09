from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.broadcast import broadcast_event
from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.draft_state import tournament_state_queryset
from app.functions.shuffle_draft import assign_next_shuffle_captain
from app.functions.teamdraft import (
    activate_round,
    advance_after_pick,
    record_pick_timing,
)
from app.models import (
    CustomUser,
    Draft,
    DraftEvent,
    DraftRound,
    Team,
    TeamDraftState,
    Tournament,
)
from app.permissions_org import can_edit_tournament
from app.serializers import (
    DraftSerializerMMRs,
    TournamentSerializer,
    _build_users_dict,
)
from app.tasks.draft_tick import evaluate_client_pick_time
from app.tasks.teamdraft_tick import start_team_tick_broadcaster_after_commit
from telemetry.logging import get_logger

log = get_logger(__name__)


def _serialize_tournament(tournament: Tournament) -> dict:
    """Serialize a tournament with the _users dict for frontend hydration.

    Re-fetches uncached with the full prefetch plan: callers respond right
    after a write, and the plan keeps the query count independent of size.
    """
    tournament = tournament_state_queryset(fresh=True).get(pk=tournament.pk)
    data = TournamentSerializer(tournament).data
    data["_users"] = _build_users_dict(tournament)
    return data


class PickPlayerForRound(serializers.Serializer):
    draft_round_pk = serializers.IntegerField(required=True)
    user_pk = serializers.IntegerField(required=True)
    client_picked_at = serializers.DateTimeField(required=False, allow_null=True)


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

    if serializer.is_valid():
        draft_round_pk = serializer.validated_data["draft_round_pk"]
        user_pk = serializer.validated_data["user_pk"]
        client_picked_at = serializer.validated_data.get("client_picked_at")
    else:
        return Response(serializer.errors, status=400)

    try:
        draft_round = DraftRound.objects.select_related("draft__tournament").get(
            pk=draft_round_pk
        )
    except DraftRound.DoesNotExist:
        return Response({"error": "Draft round not found"}, status=404)

    # Check authorization: tournament staff OR captain for this round
    is_tournament_staff = False
    if draft_round.draft and draft_round.draft.tournament:
        is_tournament_staff = can_edit_tournament(
            request.user, draft_round.draft.tournament
        )
    is_captain_for_round = draft_round.captain == request.user

    if not (is_tournament_staff or is_captain_for_round):
        log.warning(
            "pick_unauthorized",
            system="tournament",
            subsystem="draft",
            user_id=request.user.pk,
            username=request.user.username,
            draft_round_id=draft_round_pk,
            captain_username=draft_round.captain.username,
        )
        return Response(
            {
                "error": "Only tournament staff or the captain for this round can make picks"
            },
            status=403,
        )

    try:
        user = CustomUser.objects.get(pk=user_pk)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    tie_data = None
    try:
        with transaction.atomic():
            draft = Draft.objects.select_for_update().get(pk=draft_round.draft_id)
            active = draft.lock_active_round()
            draft_round = DraftRound.objects.select_for_update().get(
                pk=draft_round.pk
            )
            # Shuffle timeout skip keeps the round pk but swaps its captain.
            if not (
                is_tournament_staff or draft_round.captain_id == request.user.pk
            ):
                log.info(
                    "pick_captain_changed",
                    system="tournament",
                    subsystem="draft",
                    user_id=request.user.pk,
                    draft_round_id=draft_round.pk,
                    captain_id=draft_round.captain_id,
                )
                return Response(
                    {
                        "code": "not_active_round",
                        "active_pick_number": active.pick_number if active else None,
                    },
                    status=409,
                )
            team = Team.objects.select_for_update().filter(
                tournament=draft.tournament_id, captain_id=draft_round.captain_id
            ).first()
            tournament = draft.tournament
            options = tournament.get_draft_options(fresh=True)
            timed = options.timer_enabled

            if timed:
                if draft.state in (
                    TeamDraftState.PENDING,
                    TeamDraftState.RESUMING,
                    TeamDraftState.COMPLETED,
                ):
                    return Response(
                        {"code": "draft_not_accepting_picks", "state": draft.state},
                        status=409,
                    )
                if draft.state == TeamDraftState.PAUSED and not is_tournament_staff:
                    return Response({"code": "paused_staff_only"}, status=403)
                if active is None or draft_round.pk != active.pk:
                    return Response(
                        {
                            "code": "not_active_round",
                            "active_pick_number": (
                                active.pick_number if active else None
                            ),
                        },
                        status=409,
                    )

            if draft_round.choice_id is not None:
                return Response({"code": "already_picked"}, status=409)

            armed = (
                timed
                and draft.state == TeamDraftState.DRAFTING
                and active is not None
                and active.started_at is not None
            )
            activate_next = timed and (armed or draft.state == TeamDraftState.PAUSED)

            now = timezone.now()
            effective, _source, _age = evaluate_client_pick_time(
                now, client_picked_at, draft.pk, system="teamdraft", subsystem="timer"
            )
            if draft.state == TeamDraftState.PAUSED and draft.paused_at is not None:
                effective = min(effective, draft.paused_at)

            draft_round.pick_player(user)

            if timed and draft_round.started_at and team is not None:
                record_pick_timing(
                    draft_round,
                    team,
                    completed_at=now,
                    effective_pick_time=effective,
                    default_reserve_ms=options.reserve_time_ms,
                )

            captain = draft_round.captain
            round_team = draft_round.team
            picked_event = DraftEvent.objects.create(
                draft=draft,
                event_type="player_picked",
                actor=request.user,
                payload={
                    "pick_number": draft_round.pick_number,
                    "captain_id": captain.pk,
                    "captain_name": captain.username,
                    "captain_avatar_url": captain.avatarUrl,
                    "picked_id": user.pk,
                    "picked_name": user.username,
                    "picked_avatar_url": user.avatarUrl,
                    "team_id": round_team.pk if round_team else None,
                    "team_name": round_team.name if round_team else None,
                },
            )
            transaction.on_commit(lambda e=picked_event: broadcast_event(e))

            if draft.draft_style == "shuffle" and draft.users_remaining.exists():
                tie_data = assign_next_shuffle_captain(draft)

            advance_after_pick(draft, options, now=now, activate=activate_next)
            invalidate_after_commit(tournament, draft)
    except Exception as e:
        log.error(
            "pick_failed",
            system="tournament",
            subsystem="draft",
            draft_round_id=draft_round_pk,
            error=str(e),
        )
        return Response({"error": f"Failed to pick player. {str(e)}"}, status=500)

    response_data = _serialize_tournament(tournament)
    if tie_data:
        response_data["tie_resolution"] = tie_data
    return Response(response_data, status=201)


class CreateTournamentTeamRequestSerializer(serializers.Serializer):
    tournament_pk = serializers.IntegerField(required=True)
    user_pk = serializers.IntegerField(required=True)
    draft_order = serializers.IntegerField(
        required=False,
        help_text="Optional draft order for the team in the tournament",
        default=0,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_team_from_captain(request):
    """Create a team from a captain. Requires tournament staff access."""
    serializer = CreateTournamentTeamRequestSerializer(data=request.data)

    if serializer.is_valid():
        tournament_pk = serializer.validated_data["tournament_pk"]
        user_pk = serializer.validated_data["user_pk"]
        draft_order = serializer.validated_data.get("draft_order", 0)
    else:
        return Response(serializer.errors, status=400)

    try:
        tournament = Tournament.objects.select_related(
            "league", "league__organization"
        ).get(pk=tournament_pk)
        user = CustomUser.objects.get(pk=user_pk)

    except Tournament.DoesNotExist:
        return Response({"error": "Tournament not found"}, status=404)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    # Check tournament staff permission
    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission to create teams in this tournament"},
            status=403,
        )

        # Create a new team and add the user as a member (or captain)
    try:
        draft = tournament.draft

    except Draft.DoesNotExist:
        pass  # No draft exists, continue
    if Team.objects.filter(tournament=tournament, captain=user).exists():
        if draft_order == 0:
            log.debug(
                "captain_already_registered",
                system="tournament",
                subsystem="registration",
                user_id=user.pk,
                tournament_id=tournament.pk,
            )
            return Response(
                _serialize_tournament(tournament),
                status=201,
            )

        team = Team.objects.get(tournament=tournament, captain=user)
        team.draft_order = draft_order
        team.save()
        return Response(
            {
                "error": "User is already a captain in this tournament with a draft order"
            },
            status=201,
        )

    display_name = user.nickname or user.username
    team = Team.objects.create(
        tournament=tournament,
        name=f"{display_name}'s Team",
        captain=user,
        draft_order=draft_order,
    )
    team.members.add(user)

    # Invalidate specific tournament after team creation
    invalidate_obj(tournament)
    invalidate_obj(team)

    return Response(_serialize_tournament(tournament), status=201)


class CreateDraftRounds(serializers.Serializer):
    tournament_pk = serializers.IntegerField(required=True)
    draft_style = serializers.ChoiceField(
        choices=["snake", "normal", "shuffle"],
        required=False,
        default=None,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_draft_rounds(request):
    """Generate draft rounds for a tournament. Requires tournament staff access."""
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

    # Check tournament staff permission
    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission to generate draft rounds"},
            status=403,
        )

    try:
        draft = tournament.draft
    except Draft.DoesNotExist:
        log.debug(
            "draft_created",
            system="tournament",
            subsystem="draft",
            tournament_id=tournament.pk,
        )
        draft = Draft.objects.create(tournament=tournament)

    log.debug(
        "draft_initializing",
        system="tournament",
        subsystem="draft",
        tournament_id=tournament.pk,
    )

    # Remove all existing teams — draft init starts fresh.
    # Save captain info so we can recreate valid teams.
    valid_user_pks = set(tournament.users.values_list("pk", flat=True))
    captain_info = list(
        tournament.teams.filter(captain_id__in=valid_user_pks).values(
            "captain_id", "draft_order", "name"
        )
    )
    tournament.teams.all().delete()

    # Recreate teams from captains who are in the tournament's user pool
    for info in captain_info:
        team = Team.objects.create(
            tournament=tournament,
            captain_id=info["captain_id"],
            name=info["name"],
            draft_order=info["draft_order"],
        )
        team.members.add(info["captain_id"])

    if not captain_info:
        return Response(
            {
                "error": "Cannot initialize draft: no captains assigned. Assign captains to teams first."
            },
            status=400,
        )

    # Set draft style if provided
    draft_style = serializer.validated_data.get("draft_style")
    if draft_style:
        draft.draft_style = draft_style

    # Build draft rounds from the fresh teams
    draft.build_rounds()
    draft.save()
    tournament.draft = draft
    tournament.save()

    # Invalidate specific objects
    invalidate_obj(draft)
    invalidate_obj(tournament)

    # Dispatch Discord notification if configured
    if tournament.discord_send_draft_link:
        from events.discord.tournament_dispatch import notify_draft_started

        notify_draft_started(tournament, draft)

    return Response(_serialize_tournament(tournament), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_team(request):
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

    # Check tournament staff permission
    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission to rebuild teams"},
            status=403,
        )

    # Ensure draft exists
    try:
        draft = tournament.draft
        if not draft:
            log.debug(
                "draft_created",
                system="tournament",
                subsystem="draft",
                tournament_id=tournament.pk,
            )
            draft = Draft.objects.create(tournament=tournament)
    except Draft.DoesNotExist:
        log.debug(
            "draft_created",
            system="tournament",
            subsystem="draft",
            tournament_id=tournament.pk,
        )
        draft = Draft.objects.create(tournament=tournament)

    # Validate: tournament must have captains assigned to teams
    if not tournament.captains:
        return Response(
            {
                "error": "Cannot rebuild teams: no captains assigned. Assign captains to teams first."
            },
            status=400,
        )

    # IMPORTANT: rebuild_teams MUST be called BEFORE build_rounds
    # so that team MMR calculations use only captains, not old picks
    # Use clear_only=True when building new rounds to avoid re-adding old picks
    will_build_rounds = not draft.draft_rounds.exists()
    draft.rebuild_teams(clear_only=will_build_rounds)

    # Build rounds if they don't exist
    if will_build_rounds:
        log.debug(
            "draft_rounds_building",
            system="tournament",
            subsystem="draft",
            tournament_id=tournament.pk,
            draft_id=draft.pk,
        )
        draft.build_rounds()
    else:
        log.debug(
            "draft_rounds_exist",
            system="tournament",
            subsystem="draft",
            tournament_id=tournament.pk,
            draft_id=draft.pk,
        )

    draft.save()
    tournament.draft = draft
    tournament = Tournament.objects.get(pk=tournament_pk)
    data = _serialize_tournament(tournament)
    log.debug(
        "tournament_rebuilt",
        system="tournament",
        subsystem="draft",
        tournament_id=tournament.pk,
    )

    # Invalidate specific objects after rebuilding teams
    invalidate_obj(draft)
    invalidate_obj(tournament)

    # Dispatch Discord notification if new rounds were built
    if will_build_rounds and tournament.discord_send_draft_link:
        from events.discord.tournament_dispatch import notify_draft_started

        notify_draft_started(tournament, draft)

    return Response(data, status=201)


class DraftPredictMMRSerializer(serializers.Serializer):
    pk = serializers.IntegerField(required=True)


from cacheops import cached_as

# cached_as sites depending on CustomUser must also list BaseUserProfile
# (nickname/avatar, T1) and DotaUserProfile (positions/dota-mmr, T2) —
# enforced by user/tests/test_cacheops.py.
from user.models import BaseUserProfile, DotaUserProfile


@api_view(["POST"])
@permission_classes([AllowAny])
def get_draft_style_mmrs(request):
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
    def get_data(request):
        return DraftSerializerMMRs(draft).data

    data = get_data(request)
    return Response(data, 201)


class UndoPickSerializer(serializers.Serializer):
    draft_pk = serializers.IntegerField(required=True)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def undo_last_pick(request):
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

    if serializer.is_valid():
        draft_pk = serializer.validated_data["draft_pk"]
    else:
        return Response(serializer.errors, status=400)

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

        undone_round_had_completed_at = last_round.completed_at is not None
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

        timed_undo = options.timer_enabled and undone_round_had_completed_at
        if timed_undo and draft.state in (
            TeamDraftState.DRAFTING,
            TeamDraftState.RESUMING,
        ):
            last_round.save()
            activate_round(
                draft,
                last_round,
                options,
                now=(
                    draft.resuming_until
                    if draft.state == TeamDraftState.RESUMING
                    else timezone.now()
                ),
                armed=True,
            )
            start_team_tick_broadcaster_after_commit(draft.pk)
        elif timed_undo and draft.state == TeamDraftState.PAUSED:
            last_round.save()
            activate_round(draft, last_round, options, now=timezone.now(), armed=False)
        else:
            last_round.started_at = None
            last_round.timed_out_at = None
            last_round.save()

        if draft.draft_style == "shuffle":
            next_round = (
                draft.draft_rounds.select_for_update()
                .filter(pick_number__gt=last_round.pick_number, choice__isnull=True)
                .order_by("pick_number")
                .first()
            )
            if next_round is not None:
                next_round.captain = None
                next_round.was_tie = False
                next_round.tie_roll_data = None
                next_round.save()

        draft.save()
        invalidate_after_commit(tournament, draft)

    return Response(_serialize_tournament(tournament), status=200)
