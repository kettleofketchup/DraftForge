"""MMR change requests: nightly screenshot retention purge."""

from typing import Any

from app.internal_client import transport

PURGE_PATH = "/mmr-requests/purge-screenshots/"


def purge_mmr_screenshots() -> dict[str, Any] | None:
    resp = transport.post(PURGE_PATH, {})
    if resp is None or not resp.ok:
        return None
    try:
        return resp.json()
    except ValueError:
        transport.log.error(
            "mmr_purge_invalid_json", http_path=PURGE_PATH, **transport.LOG_BASE
        )
        return None
