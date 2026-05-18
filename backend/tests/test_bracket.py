"""Test-only endpoints for bracket scenarios that are awkward to create
through the regular API but easy to verify with Playwright.

Exposed at ``/api/tests/bracket/...`` and gated on ``isTestEnvironment``;
returns 404 in any non-test environment.
"""

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.models import Game, Team
from common.utils import isTestEnvironment


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def force_mismatched_winning_team(request):
    """Force a Game into the "stuck" state from issue #235:

      Game.status         = 'completed'
      Game.winning_team   = <a team that is NEITHER radiant_team NOR dire_team>

    Reproduces the production bug where a winner was set, then the Game's
    teams were rewritten (by ``save_bracket`` or ``advance_winner``)
    leaving ``winning_team_id`` pointing at the prior team. The frontend
    can no longer derive ``match.winner`` so both Set Winner (gated on
    status != 'completed') and the *original* Unset Winner (gated on
    match.winner being truthy) are hidden — admins stuck.

    Body::

        {"game_id": <int>}

    Picks any team in the game's tournament that's NOT already in either
    slot, assigns it as ``winning_team``, sets ``status='completed'``,
    saves. Returns the chosen winning_team_id so the caller can assert
    against it.
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    game_id = request.data.get("game_id")
    if not game_id:
        return Response(
            {"error": "game_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response(
            {"error": f"Game {game_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not game.tournament_id:
        return Response(
            {"error": f"Game {game_id} has no tournament — cannot pick another team"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    excluded_pks = {pk for pk in (game.radiant_team_id, game.dire_team_id) if pk}
    other_team = (
        Team.objects.filter(tournament_id=game.tournament_id)
        .exclude(pk__in=excluded_pks)
        .first()
    )
    if not other_team:
        return Response(
            {
                "error": "No other team available in the tournament to use as a "
                "mismatched winning_team. Add at least one extra team."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Only changes winning_team_id + status, so the pre_save Game signal
    # short-circuits (its early-return checks radiant_team_id / dire_team_id
    # only) and we don't accidentally reset an attached HeroDraft.
    game.winning_team = other_team
    game.status = "completed"
    game.save()

    return Response(
        {
            "game_id": game.pk,
            "winning_team_id": other_team.pk,
            "winning_team_name": other_team.name,
            "radiant_team_id": game.radiant_team_id,
            "dire_team_id": game.dire_team_id,
            "status": game.status,
        }
    )
