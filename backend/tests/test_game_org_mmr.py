"""Test endpoints for the per-game org MMR E2E specs (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- GET game-org-mmr/data/: the seeded org, league, tournaments, event and users.
- POST game-org-mmr/approve-setup/: rebuild the Deadlock approve event with a
  pending signup for the approve user (tests.populate.game_org_mmr).
"""

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.utils import isTestEnvironment
from tests.populate.game_org_mmr import (
    game_org_mmr_test_data,
    reset_game_org_mmr_approve,
)


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def game_org_mmr_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(game_org_mmr_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def game_org_mmr_approve_setup(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(reset_game_org_mmr_approve())
