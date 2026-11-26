"""Internal hero draft endpoints for celery workers (InternalServiceAuth)."""

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.cache_utils import invalidate_after_commit
from draft.services.hero import new_herodraft_for_game
from tournament.broadcast import bracket_changed_on_commit
from tournament.models import Game

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def list_auto_herodraft_games(request: Request) -> Response:
    """Games the auto-create sweep should draft, across every tournament.

    The tournament has auto_create_hero_drafts on and is in_progress; both
    teams are assigned, both have a captain, and the game has no hero draft yet.
    """
    games = (
        Game.objects.nocache()
        .filter(
            tournament__auto_create_hero_drafts=True,
            tournament__state="in_progress",
            radiant_team__captain__isnull=False,
            dire_team__captain__isnull=False,
            herodraft__isnull=True,
        )
        .select_related("tournament", "radiant_team", "dire_team")
        .order_by("pk")
    )
    return Response(
        [
            {
                "id": g.pk,
                "tournament_id": g.tournament_id,
                "discord_send_herodraft_link": g.tournament.discord_send_herodraft_link,
                "radiant_team_id": g.radiant_team_id,
                "radiant_team_name": g.radiant_team.name,
                "dire_team_id": g.dire_team_id,
                "dire_team_name": g.dire_team.name,
                "round": g.round,
                "has_captains": True,
            }
            for g in games
        ]
    )


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_herodraft_for_game(request: Request, game_id: int) -> Response:
    """Atomically create a HeroDraft for a game (select_for_update guard).

    Returns existing herodraft if one already exists (idempotent).
    Returns 400 if teams missing captains.
    """
    with transaction.atomic():
        game = (
            Game.objects.select_for_update()
            .select_related("radiant_team", "dire_team")
            .get(pk=game_id)
        )

        if hasattr(game, "herodraft"):
            return Response({"id": game.herodraft.pk, "created": False})

        if not game.radiant_team.captain or not game.dire_team.captain:
            return Response(
                {"error": "Both teams must have captains"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        herodraft = new_herodraft_for_game(game)
        invalidate_after_commit(game)
        bracket_changed_on_commit(game.tournament_id, game.pk)

    return Response(
        {"id": herodraft.pk, "created": True},
        status=status.HTTP_201_CREATED,
    )
