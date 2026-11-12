"""Celery-side calls to the internal lobby API (lobby.views_internal).

Workers never read the database: they go through these helpers, which use
app.internal_client's transport (X-Internal-Token, logging of failures).
Each returns the decoded JSON, or None when the backend could not be reached
or answered an error; `claim` also passes 422 answers through.
"""

from __future__ import annotations

from typing import Any

import requests

from app import internal_client as ic

BASE = "/lobbies"


def _json(resp: requests.Response | None, *, accept: tuple[int, ...] = ()) -> Any:
    if resp is None:
        return None
    if not resp.ok and resp.status_code not in accept:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def claim(
    game_id: int,
    *,
    trigger: str,
    user_id: int | None = None,
    allow_missing: bool = False,
) -> tuple[int | None, Any]:
    """(status, body) of the claim; status is None when the call failed."""
    resp = ic._post(
        f"{BASE}/games/{game_id}/claim/",
        {"trigger": trigger, "user_id": user_id, "allow_missing": allow_missing},
    )
    if resp is None:
        return None, None
    return resp.status_code, _json(resp, accept=(404, 409, 422, 503))


def accepted(pk: int, lobby: dict[str, Any], *, replayed: bool) -> Any:
    return _json(
        ic._post(f"{BASE}/{pk}/accepted/", {"lobby": lobby, "replayed": replayed})
    )


def rejected(
    pk: int, *, code: str, detail: str, retryable: bool, retry_in: int = 0
) -> Any:
    return _json(
        ic._post(
            f"{BASE}/{pk}/rejected/",
            {
                "code": code,
                "detail": detail,
                "retryable": retryable,
                "retry_in": retry_in,
            },
        )
    )


def conflict(pk: int, lobby: dict[str, Any]) -> Any:
    return _json(ic._post(f"{BASE}/{pk}/conflict/", {"lobby": lobby}))


def active() -> list[dict[str, Any]] | None:
    return _json(ic._get(f"{BASE}/active/"))


def detail(pk: int) -> dict[str, Any] | None:
    return _json(ic._get(f"{BASE}/{pk}/"))


def sync(
    pk: int,
    *,
    lobby: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    missing: bool = False,
) -> Any:
    return _json(
        ic._post(
            f"{BASE}/{pk}/sync/",
            {"lobby": lobby, "events": events or [], "missing": missing},
        )
    )


def eligible_games() -> list[dict[str, Any]] | None:
    return _json(ic._get(f"{BASE}/eligible-games/"))


def notify_info(pk: int) -> dict[str, Any] | None:
    return _json(ic._get(f"{BASE}/{pk}/notify/"))
