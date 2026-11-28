"""Org API connection sync: claim and step work through the internal API."""

from typing import Any

from app.internal_client import transport

BASE_PATH = "/org-api-sync"
CLIENT_TIMEOUT_SECONDS = 30
STEP_PATHS = {"run": "runs", "mmr_delivery": "deliveries"}


def _post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    resp = transport.post(f"{BASE_PATH}{path}", body, timeout=CLIENT_TIMEOUT_SECONDS)
    if resp is None:
        return None
    if resp.status_code == 429:
        return {"busy": True}
    if not resp.ok:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def claim(*, limit: int = 20) -> dict[str, Any] | None:
    return _post("/claim/", {"limit": limit})


def step(kind: str, work_id: str, fence: str) -> dict[str, Any] | None:
    return _post(f"/{STEP_PATHS[kind]}/{work_id}/step/", {"fence": fence})


def promotion_step() -> dict[str, Any] | None:
    return _post("/promotion/step/", {})


def cleanup() -> dict[str, Any] | None:
    return _post("/cleanup/", {})
