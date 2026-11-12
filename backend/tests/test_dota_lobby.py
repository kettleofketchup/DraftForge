"""Test endpoints for the dota_lobby E2E specs (TEST=true only).

Routes under /api/tests/ (tests/urls.py):

- POST login-dota-lobby/<role>/: log in as a dota_lobby test user. Roles:
  staff, rostered, registered, unregistered, league-staff
  (tests.data.dota_lobby.LOBBY_ROLE_USERS).
- GET dota-lobby/data/: the seeded PKs, names and fixed password.
- POST dota-lobby/reset/: close the lobbies the specs left open, end their
  rows, set the games back to pending and restore the password settings.
- GET dota-lobby/games/<game_pk>/lobby/: the game's latest lobby row with its
  dota_lobby lobby ID, so a spec can address the simulator.
- POST dota-lobby/games/<game_pk>/lobby/seed/: give a lobby test game a
  `waiting` lobby row without dota_lobby (seed_dota_lobby), for specs that
  run without the simulator. 409 with the code when the game cannot have one.
- GET dota-lobby/simulator/: whether the simulated dota_lobby answers, is
  ready and holds the test league. Specs skip when it is not available.
- GET/POST/PATCH/DELETE dota-lobby-sim/<path>: forwarded to the simulator's
  control API, /v1/sim/<path>, with the backend's API key.
"""

from __future__ import annotations

import re
from typing import Any

from django.contrib.auth import login
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

from app.models import CustomUser
from common.utils import isTestEnvironment
from lobby.models import GameLobby
from tests.data.dota_lobby import LOBBY_ROLE_USERS, LOBBY_STEAM_LEAGUE_ID
from tests.dota_lobby_sim import SimulatorUnavailable, simulator_request
from tests.populate.dota_lobby import (
    SeedRefused,
    dota_lobby_test_data,
    reset_dota_lobby_data,
    seed_dota_lobby,
)

# A /v1/sim sub-path: segments of letters, digits, '_' and '-'.
_SIM_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*/?$")


def _not_found() -> Response:
    return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)


def _unavailable(exc: SimulatorUnavailable) -> Response:
    return Response(
        {"available": False, "code": exc.code, "detail": exc.detail},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_dota_lobby(request: Request, role: str) -> Response:
    """Log in as the dota_lobby test user for `role`."""
    if not isTestEnvironment(request):
        return _not_found()
    data = LOBBY_ROLE_USERS.get(role)
    if data is None:
        return Response(
            {"detail": f"Unknown role. One of: {', '.join(LOBBY_ROLE_USERS)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = CustomUser.objects.filter(pk=data.pk).first()
    if user is None:
        return Response(
            {"detail": "Test user not populated. Run db::populate first."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response(
        {"success": True, "user": {"pk": user.pk, "username": user.username}}
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def dota_lobby_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(dota_lobby_test_data())


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_dota_lobby(request: Request) -> Response:
    if not isTestEnvironment(request):
        return _not_found()
    return Response(reset_dota_lobby_data())


def _row_payload(row: GameLobby) -> dict[str, Any]:
    return {
        "id": row.pk,
        "lobby_id": row.lobby_id,
        "gc_lobby_id": row.gc_lobby_id or None,
        "state": row.state,
        "state_reason": row.state_reason or None,
        "ended": row.ended,
        "password": row.password,
        "match_id": str(row.match_id) if row.match_id else None,
        "provisional_winner_side": row.provisional_winner_side or None,
        "last_error_code": row.last_error_code or None,
    }


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def dota_lobby_game_lobby(request: Request, game_pk: int) -> Response:
    """The game's latest lobby row, with the IDs the simulator knows it by."""
    if not isTestEnvironment(request):
        return _not_found()
    row = (
        GameLobby.objects.filter(game_id=game_pk).order_by("-created_at", "-pk").first()
    )
    return Response({"lobby": _row_payload(row) if row is not None else None})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def seed_dota_lobby_row(request: Request, game_pk: int) -> Response:
    """Give a lobby test game a `waiting` lobby row, without dota_lobby."""
    if not isTestEnvironment(request):
        return _not_found()
    try:
        row = seed_dota_lobby(game_pk)
    except SeedRefused as exc:
        return Response(
            {"detail": "The game cannot have a lobby now", "code": exc.code},
            status=status.HTTP_409_CONFLICT,
        )
    return Response({"lobby": _row_payload(row)})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def dota_lobby_simulator(request: Request) -> Response:
    """Whether the simulated dota_lobby can take the specs' lobbies now."""
    if not isTestEnvironment(request):
        return _not_found()
    try:
        ready = simulator_request("GET", "/readyz", auth=False)
        health = simulator_request("GET", "/health", auth=False)
        leagues = simulator_request("GET", "/v1/leagues")
    except SimulatorUnavailable as exc:
        return _unavailable(exc)
    verified = sorted(
        {
            league.get("league_id")
            for league in (leagues.body or {}).get("leagues", [])
            if isinstance(league, dict)
            and any(h.get("verified") for h in league.get("holders") or [])
        }
        - {None}
    )
    simulation = bool((health.body or {}).get("simulation"))
    is_ready = ready.status == 200
    return Response(
        {
            "available": simulation and is_ready and LOBBY_STEAM_LEAGUE_ID in verified,
            "ready": is_ready,
            "simulation": simulation,
            "verified_leagues": verified,
            "league_id": LOBBY_STEAM_LEAGUE_ID,
        }
    )


@csrf_exempt
@api_view(["GET", "POST", "PATCH", "DELETE"])
@authentication_classes([])
@permission_classes([AllowAny])
def dota_lobby_sim_proxy(request: Request, path: str) -> Response:
    """Forward to the simulator's control API: /v1/sim/<path>."""
    if not isTestEnvironment(request):
        return _not_found()
    if not _SIM_PATH_RE.match(path):
        return Response({"detail": "Invalid path"}, status=status.HTTP_400_BAD_REQUEST)
    body = request.data if request.method in ("POST", "PATCH") else None
    try:
        answer = simulator_request(
            request.method, f"/v1/sim/{path.rstrip('/')}", json=body or None
        )
    except SimulatorUnavailable as exc:
        return _unavailable(exc)
    return Response(answer.body, status=answer.status)
