"""HTTP access to the simulated dota_lobby, for the test endpoints only.

The test stack's dota_lobby runs in simulation mode (docker/dota-lobby/).
Its control API (/v1/sim/...) is reached with the backend's own
DOTA_LOBBY_URL and DOTA_LOBBY_API_KEY, so Playwright drives the simulator
through BASE_URL (/api/tests/dota-lobby-sim/...) and never needs the key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from config.dota_lobby import DotaLobbyConfig

TIMEOUT_SECONDS = 10.0
CONNECT_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class SimResponse:
    status: int
    body: Any


class SimulatorUnavailable(Exception):
    """DOTA_LOBBY_URL is not set, or nothing answers there."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def simulator_request(
    method: str, path: str, *, json: Any = None, auth: bool = True
) -> SimResponse:
    """`method` on `path` (from the service root, for example /v1/sim/lobbies).

    Raises SimulatorUnavailable when there is nothing to talk to. Any HTTP
    answer, errors included, is returned as it is.
    """
    config = DotaLobbyConfig.from_env()
    if not config.url:
        raise SimulatorUnavailable("not_configured", "DOTA_LOBBY_URL is not set")
    headers = {"Accept": "application/json"}
    if auth and config.api_key:
        headers["X-API-Key"] = config.api_key
    try:
        resp = requests.request(
            method,
            f"{config.url}{path}",
            json=json,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, TIMEOUT_SECONDS),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise SimulatorUnavailable("simulator_unavailable", type(exc).__name__) from exc
    try:
        body: Any = resp.json()
    except ValueError:
        body = {"detail": resp.text[:500]}
    return SimResponse(resp.status_code, body)
