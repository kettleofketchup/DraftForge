from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_obj
from app.display_names import user_display_name
from app.models import CustomUser, Team, Tournament
from app.serializers import (
    TournamentSerializer,
    build_users_dict,
    tournament_organization,
)
from org.display_names import guild_nicknames, org_nicknames_public
from telemetry.logging import get_logger
from tournament.permissions import can_edit_tournament
from tournament.state import tournament_state_queryset

log = get_logger(__name__)


def serialize_tournament(tournament: Tournament) -> dict:
    """Serialize a tournament with the _users dict for frontend hydration.

    Re-fetches uncached with the full prefetch plan: callers respond right
    after a write, and the plan keeps the query count independent of size.
    """
    tournament = tournament_state_queryset(fresh=True).get(pk=tournament.pk)
    data = TournamentSerializer(tournament, context={"fresh": True}).data
    data["_users"] = build_users_dict(tournament, fresh=True)
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
                serialize_tournament(tournament),
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

    org = tournament_organization(tournament, fresh=True)
    org_id = org.pk if org and org_nicknames_public(org.pk) else None
    display_name = user_display_name(
        user, guild_nickname=guild_nicknames(org_id, [user.pk]).get(user.pk)
    )
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

    return Response(serialize_tournament(tournament), status=201)
