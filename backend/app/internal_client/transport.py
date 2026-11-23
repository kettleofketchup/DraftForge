"""HTTP transport shared by every internal_client module: URLs, auth, error logging."""

import os

import requests
from structlog.contextvars import get_contextvars

from telemetry.logging import get_logger

log = get_logger("app.internal_client")

INTERNAL_API_URL = os.environ.get(
    "INTERNAL_API_URL",
    "http://backend:8000/api/internal",
)
# Base API URL for reads — same host, public API paths
API_BASE_URL = os.environ.get(
    "API_BASE_URL",
    "http://backend:8000/api",
)
TIMEOUT = 30

LOG_BASE: dict[str, object] = {
    "system": "internal_client",
    "subsystem": "http",
    "tags": ["internal_api", "outbound"],
    "tags_csv": "internal_api,outbound",
}


class InternalAPIUnavailable(RuntimeError):
    """A read the caller cannot safely treat as empty failed."""


def headers() -> dict[str, str]:
    result = {
        "X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", ""),
        "Content-Type": "application/json",
    }
    interaction_id = get_contextvars().get("interaction_id")
    if interaction_id:
        result["X-Discord-Interaction-ID"] = str(interaction_id)
    return result


def log_http_error(method: str, path: str, status_code: int, body_excerpt: str) -> None:
    # 4xx: server is healthy, request was rejected as expected business logic
    # (validation, "not yet parsed", duplicate-locked, etc.). 5xx: actual server
    # bug. Splitting severity keeps dashboards / alerts honest.
    log_fn = log.warning if 400 <= status_code < 500 else log.error
    log_fn(
        "internal_http_error",
        http_method=method,
        http_path=path,
        http_status_code=status_code,
        body_excerpt=body_excerpt,
        **LOG_BASE,
    )


def log_network_error(method: str, path: str, exc: BaseException) -> None:
    log.error(
        "internal_http_network_error",
        http_method=method,
        http_path=path,
        error_class=type(exc).__name__,
        error_message=str(exc),
        exc_info=True,
        **LOG_BASE,
    )


def post(path: str, data: dict) -> requests.Response | None:
    """POST to an internal endpoint. Returns response or None on network error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.post(url, json=data, headers=headers(), timeout=TIMEOUT)
        if not resp.ok:
            log_http_error("POST", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as exc:
        log_network_error("POST", path, exc)
        return None


def patch(path: str, data: dict) -> requests.Response | None:
    """PATCH an internal endpoint. Returns response or None on network error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.patch(url, json=data, headers=headers(), timeout=TIMEOUT)
        if not resp.ok:
            log_http_error("PATCH", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as exc:
        log_network_error("PATCH", path, exc)
        return None


def get(path: str, params: dict | None = None) -> requests.Response | None:
    """GET from an internal endpoint. Returns response or None on network error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=headers(), timeout=TIMEOUT)
        if not resp.ok:
            log_http_error("GET", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as exc:
        log_network_error("GET", path, exc)
        return None


def api_get(path: str, params: dict | None = None) -> requests.Response | None:
    """GET from the public API (not /internal/). Uses same auth token."""
    url = f"{API_BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=headers(), timeout=TIMEOUT)
        if not resp.ok:
            log_http_error("GET", f"(public){path}", resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as exc:
        log_network_error("GET", f"(public){path}", exc)
        return None
