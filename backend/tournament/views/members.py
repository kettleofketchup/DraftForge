"""Tournament member management API view."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import Tournament
from org.member_resolution import resolve_member_user
from tournament.functions import serialize_tournament
from tournament.permissions import can_edit_tournament


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_tournament_member(request: Request, tournament_id: int) -> Response:
    """Add a member to a tournament's users M2M."""
    tournament = get_object_or_404(
        Tournament.objects.select_related("league__organization"), pk=tournament_id
    )

    if not can_edit_tournament(request.user, tournament):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org = tournament.league.organization if tournament.league else None
    result = resolve_member_user(request.data, org=org)
    if isinstance(result, Response):
        return result
    user, _ = result

    if tournament.users.filter(pk=user.pk).exists():
        return Response(
            {"error": "User is already in this tournament"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tournament.users.add(user)

    invalidate_obj(tournament)
    invalidate_after_commit(tournament)

    tournament.refresh_from_db()
    return Response({"status": "added", "tournament": serialize_tournament(tournament)})
