"""Shared fixtures for the lobby lifecycle tests."""

from __future__ import annotations

import itertools
import json
import time
from contextlib import contextmanager
from typing import Any
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, DotaLobbyMode, Game, GameMode, Team, Tournament
from lobby.webhook import sign

TOKEN = "test-internal-token"
SECRET = "whsec_test"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}
WEBHOOK_URL = "/api/internal/lobbies/events/"

LOBBY_SETTINGS = {
    "DOTA_LOBBY_ENABLED": True,
    "DOTA_LOBBY_WEBHOOK_SECRETS": (SECRET,),
    "DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS": 300,
    "DOTA_LOBBY_REF_PREFIX": "game",
    "DOTA_LOBBY_REGION": "",
    "INTERNAL_SERVICE_TOKEN": TOKEN,
}

lobby_settings = override_settings(**LOBBY_SETTINGS)

_ids = itertools.count(1)


def make_user(*, steam: bool = True, discord: bool = True) -> CustomUser:
    n = next(_ids)
    return CustomUser.objects.create_user(
        username=f"lobby_player_{n}_{time.monotonic_ns()}",
        password="x",
        steam_account_id=40_000_000 + n if steam else None,
        discordId=str(900_000_000_000 + n) if discord else None,
    )


def make_team(tournament: Tournament, name: str, *, size: int = 5) -> Team:
    captain = make_user()
    team = Team.objects.create(tournament=tournament, name=name, captain=captain)
    team.members.add(captain, *(make_user() for _ in range(size - 1)))
    return team


def make_tournament(**fields: Any) -> Tournament:
    defaults = {
        "name": "Spring Cup",
        "date_played": timezone.now(),
        "state": "in_progress",
        "dota_lobby_mode": DotaLobbyMode.AUTO,
        "game_mode": GameMode.CAPTAINS_MODE,
    }
    defaults.update(fields)
    return Tournament.objects.create(**defaults)


def make_game(tournament: Tournament | None = None, **fields: Any) -> Game:
    """A pending game with two five-player teams, saved without signals firing
    a create (the global switch is off outside `lobby_settings`)."""
    tournament = tournament or make_tournament()
    radiant = fields.pop("radiant_team", None) or make_team(tournament, "Ravens")
    dire = fields.pop("dire_team", None) or make_team(tournament, "Owls")
    return Game.objects.create(
        tournament=tournament,
        radiant_team=radiant,
        dire_team=dire,
        round=2,
        **fields,
    )


def lobby_view(
    lobby_id: str = "lob_1",
    *,
    external_ref: str = "game:1",
    state: str = "pending",
    seq: int = 1,
    game_lobby_id: int | None = None,
    radiant_ref: str | None = None,
    dire_ref: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": lobby_id,
        "external_ref": external_ref,
        "state": state,
        "seq": seq,
        "name": "Spring Cup R2: Ravens vs Owls",
        "teams": {
            "radiant": {"team_ref": radiant_ref, "players": []},
            "dire": {"team_ref": dire_ref, "players": []},
        },
        "metadata": (
            {"game_lobby_id": str(game_lobby_id)} if game_lobby_id is not None else {}
        ),
    }
    view.update(extra)
    return view


def envelope(
    seq: int,
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    lobby_id: str = "lob_1",
    external_ref: str = "game:1",
    state: str = "waiting",
    game_lobby_id: int | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id or f"evt_{lobby_id}_{seq}",
        "type": event_type,
        "seq": seq,
        "occurred_at": "2026-11-08T18:05:00Z",
        "lobby": {
            "id": lobby_id,
            "external_ref": external_ref,
            "state": state,
            "bot": "bot1",
            "gc_lobby_id": "27110012345678901",
            "league_id": None,
            "metadata": (
                {"game_lobby_id": str(game_lobby_id)}
                if game_lobby_id is not None
                else {}
            ),
        },
        "data": data or {},
    }


def post_webhook(
    client: APIClient,
    body: dict[str, Any] | bytes,
    *,
    secret: str = SECRET,
    timestamp: int | None = None,
    token: str | None = TOKEN,
    signature: str | None = None,
) -> Any:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    ts = str(int(time.time()) if timestamp is None else timestamp)
    headers = {
        "HTTP_X_DOTA_LOBBY_TIMESTAMP": ts,
        "HTTP_X_DOTA_LOBBY_SIGNATURE": signature or sign(secret, ts, raw),
    }
    if token is not None:
        headers["HTTP_X_INTERNAL_TOKEN"] = token
    return client.generic(
        "POST", WEBHOOK_URL, raw, content_type="application/json", **headers
    )


class _BridgeResponse:
    def __init__(self, resp: Any) -> None:
        self.status_code = resp.status_code
        self.ok = 200 <= resp.status_code < 400
        self._resp = resp
        self.text = resp.content.decode(errors="replace")

    def json(self) -> Any:
        return self._resp.json()


@contextmanager
def internal_api_bridge():
    """Route app.internal_client calls into this process's test client.

    Celery tasks then run against the real internal endpoints, in the test
    transaction, as they would over HTTP in production.
    """
    client = APIClient()

    def _post(path: str, data: dict) -> _BridgeResponse:
        return _BridgeResponse(
            client.post(f"/api/internal{path}", data, format="json", **HEADERS)
        )

    def _get(path: str, params: dict | None = None) -> _BridgeResponse:
        return _BridgeResponse(
            client.get(f"/api/internal{path}", params or {}, **HEADERS)
        )

    def _patch(path: str, data: dict) -> _BridgeResponse:
        return _BridgeResponse(
            client.patch(f"/api/internal{path}", data, format="json", **HEADERS)
        )

    with (
        mock.patch("app.internal_client._post", side_effect=_post) as post,
        mock.patch("app.internal_client._get", side_effect=_get),
        mock.patch("app.internal_client._patch", side_effect=_patch),
    ):
        yield post
