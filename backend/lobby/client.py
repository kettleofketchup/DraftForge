"""HTTP client for the dota_lobby /v1 API.

Configured from the environment (config.dota_lobby), so it works in the
backend and in Celery workers. Every error is raised as DotaLobbyError; act on
its `code` and `retryable`, never on the human-readable `detail`.

dota_lobby answers errors as RFC 9457 problem+json:

    {"status": 409, "title": "Conflict", "detail": "...",
     "code": "conflict", "retryable": false, "errors": [...]}

Validation failures are 422 (`invalid_request`, with one `errors` entry per
problem). `retryable` is true only for 503 (`unavailable`) and 504
(`gc_timeout`). This client also treats a timeout or a refused connection as
retryable (`unreachable`), and a non-problem body (a proxy's HTML error page)
as `http_<status>`, retryable for 502, 503 and 504.

Calls that are safe to repeat are retried here a few times with a short
backoff when the error is retryable. Create is safe to repeat: dota_lobby keys
it on external_ref and returns the existing lobby for an identical request.
Launch, flip and invite are not retried; the caller decides.

Redirects are not followed: requests would re-send X-API-Key to whatever host
a redirect names, and turn a redirected POST into a GET. A 3xx is raised as a
permanent `http_<status>` error.

Request bodies, passwords and the API key are never logged.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any, TypeVar
from urllib.parse import quote

import requests
from pydantic import BaseModel, ValidationError

from config.dota_lobby import DotaLobbyConfig
from lobby.schemas import (
    CreateResult,
    InviteResult,
    LeagueView,
    LobbyEvent,
    LobbyView,
    ProblemError,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "lobby", "subsystem": "client"}

RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 3.0)
# Connecting gets at most this long, whatever DOTA_LOBBY_TIMEOUT_SECONDS
# says (that is the read timeout): a dota_lobby that drops packets then
# fails fast instead of holding a web worker for both timeouts.
CONNECT_TIMEOUT_SECONDS = 3.0
GATEWAY_STATUSES = frozenset({502, 503, 504})
LIST_PAGE_SIZE = 200
EVENTS_PAGE_SIZE = 500

M = TypeVar("M", bound=BaseModel)


class DotaLobbyError(Exception):
    """A failed dota_lobby call.

    `code` is dota_lobby's problem code (`conflict`, `invalid_request`,
    `league_not_held`, ...) or one of this client's: `unreachable`,
    `not_configured`, `invalid_response`, `request_failed`, `http_<status>`.
    """

    def __init__(
        self,
        code: str,
        *,
        status: int | None = None,
        retryable: bool = False,
        title: str = "",
        detail: str = "",
        errors: list[ProblemError] | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.code = code
        self.status = status
        self.retryable = retryable
        self.title = title
        self.detail = detail
        self.errors = errors or []
        self.retry_after = retry_after
        super().__init__(f"{status or '-'} {code}: {detail or title or code}")


class DotaLobbyUnavailable(DotaLobbyError):
    """dota_lobby did not answer (timeout or connection error)."""

    def __init__(self, detail: str) -> None:
        super().__init__("unreachable", retryable=True, detail=detail)


class DotaLobbyNotConfigured(DotaLobbyError):
    """DOTA_LOBBY_URL is not set."""

    def __init__(self) -> None:
        super().__init__("not_configured", detail="DOTA_LOBBY_URL is not set")


def _retry_after(resp: requests.Response) -> int | None:
    raw = resp.headers.get("Retry-After", "").strip()
    return int(raw) if raw.isdigit() else None


def error_from_response(resp: requests.Response) -> DotaLobbyError:
    """Build a DotaLobbyError from a non-2xx response."""
    status = resp.status_code
    body: object = None
    if "json" in resp.headers.get("Content-Type", ""):
        try:
            body = resp.json()
        except ValueError:
            body = None
    if isinstance(body, dict) and isinstance(body.get("code"), str):
        errors = _problem_errors(body.get("errors"))
        return DotaLobbyError(
            body["code"],
            status=status,
            retryable=body.get("retryable") is True,
            title=str(body.get("title") or ""),
            detail=str(body.get("detail") or ""),
            errors=errors,
            retry_after=_retry_after(resp),
        )
    return DotaLobbyError(
        f"http_{status}",
        status=status,
        retryable=status in GATEWAY_STATUSES,
        title=resp.reason or "",
        retry_after=_retry_after(resp),
    )


def _problem_errors(raw_errors: object) -> list[ProblemError]:
    """The problem's `errors` entries, skipping any that are malformed."""
    if not isinstance(raw_errors, list):
        return []
    errors = []
    for raw in raw_errors:
        if not isinstance(raw, dict):
            continue
        try:
            errors.append(ProblemError.model_validate(raw))
        except ValidationError:
            continue
    return errors


class DotaLobbyClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        backoff: tuple[float, ...] = RETRY_BACKOFF_SECONDS,
    ) -> None:
        config = DotaLobbyConfig.from_env()
        self.base_url = (base_url if base_url is not None else config.url).rstrip("/")
        if not self.base_url:
            raise DotaLobbyNotConfigured()
        self.timeout = timeout if timeout is not None else config.timeout_seconds
        self._sleep = sleep
        self._backoff = backoff
        self.session = session or requests.Session()
        key = api_key if api_key is not None else config.api_key
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": _user_agent()}
        )
        if key:
            self.session.headers["X-API-Key"] = key

    # ---- lobbies ----

    def create_lobby(self, body: Mapping[str, Any]) -> CreateResult:
        """POST /v1/lobbies. 202 is a new lobby, 200 a repeat of an active one."""
        resp = self._request("POST", "/v1/lobbies", json=dict(body))
        lobby = self._parse(resp, LobbyView)
        return CreateResult(lobby=lobby, replayed=resp.status_code == 200)

    def get_lobby(self, lobby_id: str) -> LobbyView:
        """GET /v1/lobbies/{id}, password included."""
        return self._parse(self._request("GET", _lobby_path(lobby_id)), LobbyView)

    def list_lobbies(
        self,
        *,
        external_ref: str | None = None,
        active: bool | None = None,
        state: list[str] | None = None,
        limit: int = LIST_PAGE_SIZE,
    ) -> Iterator[LobbyView]:
        """GET /v1/lobbies, newest first, following next_cursor."""
        params: dict[str, str | int] = {"limit": limit}
        if external_ref is not None:
            params["external_ref"] = external_ref
        if active is not None:
            params["active"] = "true" if active else "false"
        if state:
            params["state"] = ",".join(state)
        while True:
            data = self._json(self._request("GET", "/v1/lobbies", params=dict(params)))
            for raw in data.get("lobbies") or []:
                yield self._validate(raw, LobbyView)
            cursor = data.get("next_cursor")
            if not cursor:
                return
            params["cursor"] = cursor

    def close_lobby(self, lobby_id: str) -> LobbyView:
        """DELETE /v1/lobbies/{id}. Safe to repeat."""
        return self._parse(self._request("DELETE", _lobby_path(lobby_id)), LobbyView)

    def launch_lobby(self, lobby_id: str, *, force: bool = False) -> LobbyView:
        """POST /v1/lobbies/{id}/launch. Not retried."""
        body = {"force": True} if force else {}
        resp = self._request(
            "POST", _lobby_path(lobby_id, "launch"), json=body, retry=False
        )
        return self._parse(resp, LobbyView)

    def invite(
        self,
        lobby_id: str,
        *,
        players: list[int] | None = None,
        missing: bool = False,
    ) -> InviteResult:
        """POST /v1/lobbies/{id}/invite: the given players, or every missing one.

        Not retried: each attempt counts against dota_lobby's per-player invite
        cap and resend cooldown, so a repeat after a lost response would come
        back as 429 `invite_limited` for invites that did go out.
        """
        if not players and not missing:
            raise ValueError("give players or missing=True")
        body: dict[str, Any] = {"missing": True} if missing else {"players": players}
        resp = self._request(
            "POST", _lobby_path(lobby_id, "invite"), json=body, retry=False
        )
        return self._parse(resp, InviteResult)

    def flip_teams(self, lobby_id: str) -> LobbyView:
        """POST /v1/lobbies/{id}/teams/flip. Not retried: a repeat flips back."""
        resp = self._request(
            "POST", _lobby_path(lobby_id, "teams", "flip"), json={}, retry=False
        )
        return self._parse(resp, LobbyView)

    def list_events(self, lobby_id: str, after: int = 0) -> Iterator[LobbyEvent]:
        """GET /v1/lobbies/{id}/events with seq above `after`, oldest first."""
        path = _lobby_path(lobby_id, "events")
        while True:
            params = {"after": after, "limit": EVENTS_PAGE_SIZE}
            data = self._json(self._request("GET", path, params=params))
            events = data.get("events") or []
            for raw in events:
                yield self._validate(raw, LobbyEvent)
            next_after = data.get("next_after")
            if not events or not isinstance(next_after, int) or next_after <= after:
                return
            after = next_after

    # ---- leagues ----

    def get_league(self, league_id: int) -> LeagueView:
        """GET /v1/leagues/{id}: which bots hold the league, and how many are free."""
        return self._parse(
            self._request("GET", f"/v1/leagues/{int(league_id)}"), LeagueView
        )

    # ---- transport ----

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        retry: bool = True,
    ) -> requests.Response:
        attempts = 1 + (len(self._backoff) if retry else 0)
        for attempt in range(1, attempts + 1):
            try:
                return self._send(method, path, json=json, params=params)
            except DotaLobbyError as exc:
                last = attempt == attempts
                (log.warning if last or not exc.retryable else log.info)(
                    "dota_lobby_request_failed",
                    http_method=method,
                    http_path=path,
                    http_status_code=exc.status,
                    code=exc.code,
                    retryable=exc.retryable,
                    detail=exc.detail,
                    attempt=attempt,
                    will_retry=exc.retryable and not last,
                    **_LOG,
                )
                if last or not exc.retryable:
                    raise
                self._sleep(self._backoff[attempt - 1])
        raise AssertionError("unreachable")  # pragma: no cover

    def _send(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None,
        params: Mapping[str, Any] | None,
    ) -> requests.Response:
        try:
            resp = self.session.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                params=params,
                timeout=(min(CONNECT_TIMEOUT_SECONDS, self.timeout), self.timeout),
                allow_redirects=False,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise DotaLobbyUnavailable(type(exc).__name__) from exc
        except requests.RequestException as exc:
            raise DotaLobbyError("request_failed", detail=type(exc).__name__) from exc
        if not 200 <= resp.status_code < 300:
            raise error_from_response(resp)
        return resp

    def _json(self, resp: requests.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise DotaLobbyError(
                "invalid_response",
                status=resp.status_code,
                detail="response body is not a JSON object",
            )
        return data

    def _parse(self, resp: requests.Response, model: type[M]) -> M:
        return self._validate(self._json(resp), model)

    def _validate(self, raw: object, model: type[M]) -> M:
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            raise DotaLobbyError(
                "invalid_response",
                detail=f"{model.__name__}: {exc.error_count()} validation error(s)",
            ) from exc


def _lobby_path(lobby_id: str, *parts: str) -> str:
    return "/".join(("/v1/lobbies", quote(lobby_id, safe=""), *parts))


def _user_agent() -> str:
    version = os.environ.get("DEPLOY_VERSION", "").strip()
    return f"draftforge/{version}" if version else "draftforge"
