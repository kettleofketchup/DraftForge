"""Internal tournament reads for Celery tasks and the Discord bot.

All endpoints require InternalServiceAuth (X-Internal-Token header).
"""

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.models import CustomUser
from tournament.models import Game, Tournament

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_tournament_for_task(request: Request, tournament_id: int) -> Response:
    """Get tournament config data for Celery tasks."""

    try:
        t = Tournament.objects.select_related("league").get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "organization_id": t.league.organization_id if t.league else None,
            "id": t.pk,
            "name": t.name,
            "state": t.state,
            "date_played": t.date_played.isoformat() if t.date_played else None,
            "auto_create_hero_drafts": t.auto_create_hero_drafts,
            "discord_send_draft_link": t.discord_send_draft_link,
            "discord_send_herodraft_link": t.discord_send_herodraft_link,
            "tournament_type": t.tournament_type,
            "draft_type": t.draft_type,
        }
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_tournament_participants(request: Request, tournament_id: int) -> Response:
    """Get tournament participants with Discord IDs (for DM sending).

    Returns the full tournament membership pool (``Tournament.users``) —
    captains and undrafted participants alike. A roster-based query
    (``Team.members``) would miss the undrafted pool: at draft-start time
    only captains have been seeded onto team rosters.
    """

    users = (
        CustomUser.objects.filter(
            tournaments=tournament_id,
            discordId__isnull=False,
        )
        .exclude(discordId="")
        .distinct()
        .values("pk", "discordId", "username")
    )
    return Response(
        [
            {
                "user_pk": u["pk"],
                "discord_id": u["discordId"],
                "username": u["username"] or "",
            }
            for u in users
        ]
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_match_participants(request: Request, game_id: int) -> Response:
    """Get players from both teams in a match (for hero draft DMs)."""

    try:
        game = Game.objects.select_related("radiant_team", "dire_team").get(pk=game_id)
    except Game.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    users = (
        CustomUser.objects.filter(
            teams_as_member__in=[game.radiant_team, game.dire_team],
            discordId__isnull=False,
        )
        .exclude(discordId="")
        .distinct()
        .values("pk", "discordId", "username")
    )
    return Response(
        [
            {
                "user_pk": u["pk"],
                "discord_id": u["discordId"],
                "username": u["username"] or "",
            }
            for u in users
        ]
    )
