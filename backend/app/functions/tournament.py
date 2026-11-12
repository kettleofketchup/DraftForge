from cacheops import cached_as
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_obj
from app.draft_state import tournament_state_queryset
from app.models import CustomUser, Draft, Team, Tournament
from app.permissions_org import can_edit_tournament
from app.serializers import (
    DraftSerializerMMRs,
    TournamentSerializer,
    _build_users_dict,
)
from telemetry.logging import get_logger
from user.models import BaseUserProfile, DotaUserProfile

log = get_logger(__name__)


def _serialize_tournament(tournament: Tournament) -> dict:
    """Serialize a tournament with the _users dict for frontend hydration.

    Re-fetches uncached with the full prefetch plan: callers respond right
    after a write, and the plan keeps the query count independent of size.
    """
    tournament = tournament_state_queryset(fresh=True).get(pk=tournament.pk)
    data = TournamentSerializer(tournament, context={"fresh": True}).data
    data["_users"] = _build_users_dict(tournament, fresh=True)
    return data


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
def create_team_from_captain(request: Request) -> Response:
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
def generate_draft_rounds(request: Request) -> Response:
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
