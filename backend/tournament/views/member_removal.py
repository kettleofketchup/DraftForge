"""Remove a single tournament member."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from telemetry.logging import get_logger
from tournament.functions import serialize_tournament
from tournament.models import Tournament
from tournament.permissions import can_edit_tournament
from tournament.serializers.tournament import delete_pre_draft_captain_teams

log = get_logger(__name__)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_tournament_member(
    request: Request, tournament_id: int, user_id: int
) -> Response:
    """Remove one member from a tournament's users M2M, leaving the others."""
    tournament = get_object_or_404(
        Tournament.objects.select_related("league__organization"), pk=tournament_id
    )

    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        user = tournament.users.nocache().filter(pk=user_id).first()
        if user is None:
            return Response(
                {
                    "error": "User is not in this tournament",
                    "code": "not_a_member",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        delete_pre_draft_captain_teams(tournament, {user.pk})
        tournament.users.remove(user)

    log.info(
        "tournament_member_removed",
        system="tournament",
        subsystem="members",
        tournament_id=tournament.pk,
        user_id=user.pk,
        actor_id=request.user.pk,
    )
    invalidate_obj(tournament)
    invalidate_after_commit(tournament)

    tournament.refresh_from_db()
    return Response(
        {"status": "removed", "tournament": serialize_tournament(tournament)}
    )
