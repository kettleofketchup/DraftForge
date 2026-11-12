"""Organizer and player API for a game's dota_lobby lobby.

Routes under `api/games/<game_pk>/lobby/`, next to `create-herodraft`:

- `GET` (signed in): the game's current lobby, or its latest one. The
  password, the per-player invite status and the error detail are only for
  the game's rostered players and tournament staff. Everyone else gets the
  state, the match ID and the provisional result.
- `POST` (tournament staff): request a lobby, or retry one that ended.
  `replace` first closes an active lobby that has not started; `replay`
  hosts a match again after its lobby played it to a result.
- `DELETE` (tournament staff): close the active lobby before its match.
- `POST invite/`: staff invite the missing players or the given ones; a
  rostered player can only invite themselves.
- `POST launch/` (tournament staff): start the match, `force` to start it
  short-handed or before every player is ready.

Invite and launch call dota_lobby synchronously and answer its errors as
`{error, code, retryable}` with dota_lobby's status. Each user gets a few of
them a minute (`429 rate_limited` after that), so repeated clicks while
dota_lobby hangs cannot tie up every web worker. The create itself runs in
Celery (lobby.tasks.create_dota_lobby), so `POST` answers 202.
"""

from __future__ import annotations

import math
from typing import Any

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from app.models import CustomUser, DotaLobbyMode, Game, Team
from app.permissions_org import IsTournamentStaff, can_edit_tournament
from lobby import broadcast, events, services, states
from lobby.client import DotaLobbyClient, DotaLobbyError
from lobby.models import GameLobby
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "lobby", "subsystem": "views"}

# Upstream statuses passed to the browser as they are. Anything else (a
# 401/403 from a wrong API key, a 3xx, an unexpected 5xx) is DraftForge's
# configuration problem, not the user's: it becomes 502.
PASSTHROUGH_STATUSES = frozenset({400, 404, 409, 422, 429, 503, 504})
# Client-side codes with no HTTP status from dota_lobby.
LOCAL_ERROR_STATUSES = {"unreachable": 503, "not_configured": 503}

REPLACED = "replaced"
CLOSED_BY_STAFF = "closed_by_staff"


class LobbyActionThrottle(UserRateThrottle):
    """Per user and action: the synchronous dota_lobby calls (invite, launch).

    Uses the default cache (Redis in production).
    """

    rate = "12/min"

    def __init__(self, scope: str) -> None:
        self.scope = scope
        super().__init__()


def _throttled(request: Request, view: APIView, scope: str) -> Response | None:
    """The 429 to answer when the user has used up `scope`, else None."""
    throttle = LobbyActionThrottle(scope)
    if throttle.allow_request(request, view):
        return None
    log.info("lobby_action_throttled", action=scope, user_id=request.user.pk, **_LOG)
    response = _error(
        "Too many lobby requests. Try again shortly.",
        "rate_limited",
        429,
        retryable=True,
    )
    wait = throttle.wait()
    if wait:
        response["Retry-After"] = str(math.ceil(wait))
    return response


def _error(message: str, code: str, http_status: int, **extra: Any) -> Response:
    return Response({"error": message, "code": code, **extra}, status=http_status)


def _upstream_error(exc: DotaLobbyError, *, game_pk: int, action: str) -> Response:
    """dota_lobby's problem as `{error, code, retryable}` with its status."""
    if exc.status in PASSTHROUGH_STATUSES:
        http_status = exc.status
    else:
        http_status = LOCAL_ERROR_STATUSES.get(exc.code, 502)
    log.warning(
        "lobby_action_failed",
        game_id=game_pk,
        action=action,
        code=exc.code,
        upstream_status=exc.status,
        retryable=exc.retryable,
        **_LOG,
    )
    body: dict[str, Any] = {
        "error": exc.detail or exc.title or exc.code,
        "code": exc.code,
        "retryable": exc.retryable,
    }
    if exc.errors:
        body["errors"] = [e.model_dump() for e in exc.errors]
    response = Response(body, status=http_status)
    if exc.retry_after is not None:
        response["Retry-After"] = str(exc.retry_after)
    return response


def _display_name(user: CustomUser) -> str:
    return user.nickname or user.username or f"User {user.pk}"


def _load_game(game_pk: int) -> Game:
    return get_object_or_404(
        Game.objects.select_related("tournament__league", "radiant_team", "dire_team"),
        pk=game_pk,
    )


def _team_queryset() -> Any:
    return Team.objects.select_related("captain").prefetch_related(
        Prefetch("members", queryset=CustomUser.objects.order_by("pk"))
    )


def latest_lobby(game: Game) -> GameLobby | None:
    """The game's active lobby, or the one it had last."""
    return services.active_lobby(game) or game.lobbies.first()


def _lobby_teams(game: Game, game_lobby: GameLobby | None) -> list[tuple[str, Team]]:
    """(side, team) for the lobby's sides, else the game's bracket slots."""
    if game_lobby is not None and game_lobby.radiant_team_id:
        ids = {"radiant": game_lobby.radiant_team_id, "dire": game_lobby.dire_team_id}
    else:
        ids = {"radiant": game.radiant_team_id, "dire": game.dire_team_id}
    teams = _team_queryset().in_bulk([pk for pk in ids.values() if pk])
    return [(side, teams[pk]) for side, pk in ids.items() if pk in teams]


def is_rostered(user: CustomUser, game: Game, game_lobby: GameLobby | None) -> bool:
    """The user plays in this game (either team, by slot or by lobby side)."""
    if not user.is_authenticated:
        return False
    team_ids = {game.radiant_team_id, game.dire_team_id}
    if game_lobby is not None:
        team_ids |= {game_lobby.radiant_team_id, game_lobby.dire_team_id}
    team_ids.discard(None)
    if not team_ids:
        return False
    return (
        Team.objects.filter(pk__in=team_ids, members=user).exists()
        or Team.objects.filter(pk__in=team_ids, captain=user).exists()
    )


def _players(game: Game, game_lobby: GameLobby | None) -> list[dict[str, Any]]:
    """Rostered players with their dota_lobby invite and seat status."""
    status_by_account = (game_lobby.players or {}) if game_lobby else {}
    rows: list[dict[str, Any]] = []
    for side, team in _lobby_teams(game, game_lobby):
        for user in services.team_roster(team):
            account_id = user.steam_account_id
            entry = status_by_account.get(str(account_id), {}) if account_id else {}
            rows.append(
                {
                    "user_id": user.pk,
                    "name": _display_name(user),
                    "side": side,
                    "team_id": team.pk,
                    "captain": user.pk == team.captain_id,
                    "account_id": account_id,
                    "status": entry.get("status") or "",
                    "seat": entry.get("seat"),
                    "ready": bool(entry.get("ready")),
                    "invites_sent": int(entry.get("invites_sent") or 0),
                    "last_invite_at": entry.get("last_invite_at"),
                }
            )
    return rows


def _team(team: Team | None) -> dict[str, Any] | None:
    return {"id": team.pk, "name": team.name} if team is not None else None


def serialize_lobby(
    game: Game, game_lobby: GameLobby, *, private: bool
) -> dict[str, Any]:
    """The lobby for the UI. `private` adds what only players and staff see."""
    data: dict[str, Any] = {
        "id": game_lobby.pk,
        "state": game_lobby.state,
        "ended": game_lobby.ended,
        "match_id": str(game_lobby.match_id) if game_lobby.match_id else None,
        "radiant_team": _team(game_lobby.radiant_team),
        "dire_team": _team(game_lobby.dire_team),
        "provisional_winner_side": game_lobby.provisional_winner_side or None,
        "provisional_winner_team_id": game_lobby.provisional_winner_team_id,
        "provisional_outcome_name": game_lobby.provisional_outcome_name or None,
        "provisional_scored": game_lobby.provisional_scored,
        "duration_seconds": game_lobby.duration_seconds,
        "match_started_at": game_lobby.match_started_at,
        "match_ended_at": game_lobby.match_ended_at,
        "updated_at": game_lobby.updated_at,
    }
    if not private:
        return data
    request = game_lobby.request or {}
    password: str | None = None
    if game_lobby.state not in states.ENDED_STATES:
        password = game_lobby.password or None
    data.update(
        {
            "state_reason": game_lobby.state_reason or None,
            "trigger": game_lobby.trigger,
            "name": request.get("name") or None,
            "game_mode": request.get("game_mode"),
            "region": request.get("region"),
            "launch": request.get("launch"),
            "league_id": game_lobby.league_id,
            "league_verified": game_lobby.league_verified,
            "bot": game_lobby.bot or None,
            "password": password,
            "players": _players(game, game_lobby),
            "pending_invites": list(game_lobby.pending_invites or []),
            "launch_attempts": game_lobby.launch_attempts,
            "last_error_code": game_lobby.last_error_code or None,
            "last_error_detail": game_lobby.last_error_detail or None,
            "last_error_at": game_lobby.last_error_at,
            "created_at": game_lobby.created_at,
            "ended_at": game_lobby.ended_at,
        }
    )
    return data


def _missing_players(user_ids: list[int]) -> list[dict[str, Any]]:
    users = CustomUser.objects.filter(pk__in=user_ids).order_by("pk")
    return [{"id": u.pk, "name": _display_name(u)} for u in users]


def _eligibility_body(eligibility: services.Eligibility) -> dict[str, Any]:
    details = dict(eligibility.details)
    if eligibility.code == "missing_steam_ids":
        details["players"] = _missing_players(list(details.get("user_ids") or []))
    return {"ok": eligibility.ok, "code": eligibility.code or None, "details": details}


def lobby_response(request: Request, game: Game) -> dict[str, Any]:
    game_lobby = latest_lobby(game)
    tournament = game.tournament
    staff = tournament is not None and can_edit_tournament(request.user, tournament)
    private = staff or is_rostered(request.user, game, game_lobby)
    mode = tournament.dota_lobby_mode if tournament else DotaLobbyMode.OFF
    body: dict[str, Any] = {
        "game_id": game.pk,
        "enabled": services.is_enabled() and mode != DotaLobbyMode.OFF,
        "mode": mode,
        "can_manage": staff,
        "is_player": private and not staff,
        "lobby": (
            serialize_lobby(game, game_lobby, private=private)
            if game_lobby is not None
            else None
        ),
    }
    if staff:
        eligibility = services.lobby_eligibility(
            game, trigger=GameLobby.Trigger.MANUAL, allow_missing=False
        )
        body["eligibility"] = _eligibility_body(eligibility)
        if game_lobby is None or game_lobby.ended:
            body["players"] = _players(game, None)
    return body


def _active_for_action(game: Game) -> tuple[GameLobby | None, Response | None]:
    """The active lobby dota_lobby already knows, or the error to answer."""
    if not services.is_enabled():
        return None, _error("Lobbies are disabled", "lobby_disabled", 400)
    game_lobby = services.active_lobby(game)
    if game_lobby is None:
        return None, _error("This game has no active lobby", "no_active_lobby", 404)
    if not game_lobby.lobby_id:
        return None, _error(
            "The lobby is still being created", "lobby_not_created", 409
        )
    return game_lobby, None


def _apply_view(pk: int, view: Any) -> GameLobby | None:
    """Apply a lobby snapshot dota_lobby returned, as the reconcile task does."""
    with transaction.atomic():
        row = (
            GameLobby.objects.select_for_update()
            .select_related("game")
            .filter(pk=pk)
            .first()
        )
        if row is None:
            return None
        if row.lobby_id == view.id and events.apply_snapshot(row, view):
            broadcast.lobby_changed_on_commit(row, bracket_changed=False)
        return row


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True


class _StaffForWrites(permissions.BasePermission):
    """Reads need a signed-in user; writes need tournament staff."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsTournamentStaff().has_permission(request, view)


class GameLobbyView(APIView):
    permission_classes = [_StaffForWrites]

    def get(self, request: Request, game_pk: int) -> Response:
        game = _load_game(game_pk)
        return Response(lobby_response(request, game))

    def post(self, request: Request, game_pk: int) -> Response:
        """Request a lobby, or retry. `{allow_missing?, replace?, replay?}`."""
        allow_missing = _bool(request.data.get("allow_missing"))
        replace = _bool(request.data.get("replace"))
        replay = _bool(request.data.get("replay"))
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update().select_related(
                    "tournament__league", "radiant_team", "dire_team"
                ),
                pk=game_pk,
            )
            active = services.active_lobby(game)
            if active is not None:
                if not replace:
                    return _error(
                        "This game already has an active lobby",
                        "active_lobby_exists",
                        409,
                        state=active.state,
                    )
                if not services.close_lobby(active, REPLACED):
                    return _error(
                        "The lobby's match has started; it cannot be replaced",
                        "lobby_in_progress",
                        409,
                        state=active.state,
                    )
            eligibility = services.queue_create(
                game,
                user_id=request.user.pk,
                allow_missing=allow_missing,
                replay=replay,
            )
            if not eligibility.ok:
                problem = _error(
                    "This game cannot get a lobby now",
                    eligibility.code,
                    400,
                    eligibility=_eligibility_body(eligibility),
                )
                # Roll back a replace: the old lobby stays as it was.
                transaction.set_rollback(True)
                return problem
        log.info(
            "lobby_create_requested",
            game_id=game.pk,
            user_id=request.user.pk,
            replace=replace,
            replay=replay,
            allow_missing=allow_missing,
            **_LOG,
        )
        return Response(
            {"queued": True, "replaced": active is not None},
            status=status.HTTP_202_ACCEPTED,
        )

    def delete(self, request: Request, game_pk: int) -> Response:
        """Close the active lobby before its match starts."""
        with transaction.atomic():
            game = get_object_or_404(Game.objects.select_for_update(), pk=game_pk)
            active = services.active_lobby(game)
            if active is None:
                return _error("This game has no active lobby", "no_active_lobby", 404)
            if not services.close_lobby(active, CLOSED_BY_STAFF):
                return _error(
                    "The lobby's match has started; it cannot be closed",
                    "lobby_in_progress",
                    409,
                    state=active.state,
                )
            broadcast.lobby_changed_on_commit(active, bracket_changed=False)
        log.info(
            "lobby_closed_by_staff",
            game_id=game.pk,
            game_lobby_id=active.pk,
            user_id=request.user.pk,
            **_LOG,
        )
        return Response(lobby_response(request, _load_game(game_pk)))


class GameLobbyInviteView(APIView):
    """Staff: `{missing: true}` or `{players: [account_id, ...]}`.

    A rostered player: `{}`, which invites only themselves.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, game_pk: int) -> Response:
        throttled = _throttled(request, self, "lobby_invite")
        if throttled is not None:
            return throttled
        game = _load_game(game_pk)
        game_lobby, problem = _active_for_action(game)
        if problem is not None:
            return problem
        tournament = game.tournament
        staff = tournament is not None and can_edit_tournament(request.user, tournament)
        missing = False
        players: list[int] | None = None
        if staff:
            missing = _bool(request.data.get("missing"))
            raw = request.data.get("players")
            if not missing:
                if not isinstance(raw, list) or not raw:
                    return _error(
                        "Give players or missing: true", "invalid_request", 400
                    )
                if not all(isinstance(p, int) and not isinstance(p, bool) for p in raw):
                    return _error(
                        "players must be Steam account IDs", "invalid_request", 400
                    )
                players = list(raw)
        else:
            if not is_rostered(request.user, game, game_lobby):
                return _error(
                    "Only this game's players and tournament staff can send invites",
                    "forbidden",
                    403,
                )
            if request.user.steam_account_id is None:
                return _error(
                    "Link your Steam account to get a lobby invite",
                    "missing_steam_id",
                    400,
                )
            players = [int(request.user.steam_account_id)]

        try:
            result = DotaLobbyClient().invite(
                game_lobby.lobby_id, players=players, missing=missing
            )
        except DotaLobbyError as exc:
            return _upstream_error(exc, game_pk=game.pk, action="invite")
        log.info(
            "lobby_invite_sent",
            game_id=game.pk,
            game_lobby_id=game_lobby.pk,
            invited=len(result.invited),
            skipped=len(result.skipped),
            by_staff=staff,
            **_LOG,
        )
        return Response(result.model_dump())


class GameLobbyLaunchView(APIView):
    """Tournament staff start the match. `{force?}`."""

    permission_classes = [IsTournamentStaff]

    def post(self, request: Request, game_pk: int) -> Response:
        throttled = _throttled(request, self, "lobby_launch")
        if throttled is not None:
            return throttled
        game = _load_game(game_pk)
        game_lobby, problem = _active_for_action(game)
        if problem is not None:
            return problem
        force = _bool(request.data.get("force"))
        try:
            view = DotaLobbyClient().launch_lobby(game_lobby.lobby_id, force=force)
        except DotaLobbyError as exc:
            return _upstream_error(exc, game_pk=game.pk, action="launch")
        _apply_view(game_lobby.pk, view)
        log.info(
            "lobby_launch_requested",
            game_id=game.pk,
            game_lobby_id=game_lobby.pk,
            force=force,
            user_id=request.user.pk,
            **_LOG,
        )
        return Response(lobby_response(request, _load_game(game_pk)))
