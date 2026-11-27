"""TEST-only endpoints for the Discord permission badge E2E specs.

GET /api/tests/discord-permissions/data/ returns the isolated data lookup.
POST /api/tests/discord-permissions/reset/ restores data and the default scenario.
POST /api/tests/discord-permissions/scenario/ selects a named canned response set.
"""

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.utils import isTestEnvironment
from tests.data.discord_permissions import PERMISSION_SCENARIO_NAMES
from tests.populate.discord_permissions import (
    discord_permissions_test_data,
    reset_discord_permissions_data,
    set_permission_scenario,
)


def _allowed(request: Request) -> bool:
    return settings.TEST and isTestEnvironment(request)


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=404)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def discord_permissions_data(request: Request) -> Response:
    if not _allowed(request):
        return _not_found()
    return Response(discord_permissions_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_discord_permissions(request: Request) -> Response:
    if not _allowed(request):
        return _not_found()
    reset_discord_permissions_data()
    return Response(discord_permissions_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def set_discord_permission_scenario(request: Request) -> Response:
    if not _allowed(request):
        return _not_found()
    name = request.data.get("scenario") if isinstance(request.data, dict) else None
    if not isinstance(name, str) or name not in PERMISSION_SCENARIO_NAMES:
        return Response({"error": "Unknown permission scenario"}, status=400)
    set_permission_scenario(name)
    return Response(discord_permissions_test_data())
