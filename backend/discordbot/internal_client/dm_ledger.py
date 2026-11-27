"""HTTP clients for the DM ledger endpoints (``discordbot/internal_dm_views.py``).

``transport`` swallows every ``requests.RequestException`` and returns None, so
a None response or a 5xx is retried with the same body (same ``claim_token``).
"""

import time

import requests
from pydantic import ValidationError

from app.internal_client import transport
from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMStatus
from discordbot.schemas import (
    DMClaimBody,
    DMClickBody,
    DMFinalizeBody,
    DMLedgerRowResponse,
    DMSendingBody,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_RETRY_DELAYS: tuple[float, ...] = (0.5, 2.0)
_LOG = {"system": "discord", "subsystem": "dm"}


def _retryable(resp: requests.Response | None) -> bool:
    return resp is None or resp.status_code >= 500


def _post(path: str, payload: dict[str, object]) -> requests.Response | None:
    resp = transport.post(path, payload)
    for delay in _RETRY_DELAYS:
        if not _retryable(resp):
            return resp
        time.sleep(delay)
        resp = transport.post(path, payload)
    return None if _retryable(resp) else resp


def _row(resp: requests.Response) -> DMLedgerRowResponse | None:
    try:
        return DMLedgerRowResponse.model_validate(resp.json())
    except (ValueError, ValidationError):
        log.error("dm_ledger_bad_response", **_LOG, http_status_code=resp.status_code)
        return None


def claim_dm(body: DMClaimBody) -> ClaimResult | None:
    resp = _post("/discord/dms/claim/", body.model_dump(mode="json"))
    if resp is None:
        return None
    if resp.status_code not in (200, 201, 409):
        log.error(
            "dm_ledger_claim_rejected",
            **_LOG,
            dm_kind=body.kind,
            http_status_code=resp.status_code,
        )
        return None
    row = _row(resp)
    if row is None:
        return None
    granted = resp.status_code != 409
    return ClaimResult(
        id=row.id,
        granted=granted,
        status=DMStatus(row.status),
        attempts=row.attempts,
        created=resp.status_code == 201,
    )


def mark_dm_sending(dm_id: int, *, claim_token: str) -> bool | None:
    body = DMSendingBody(claim_token=claim_token)
    resp = _post(f"/discord/dms/{dm_id}/sending/", body.model_dump(mode="json"))
    if resp is None:
        return None
    if resp.status_code == 204:
        return True
    if resp.status_code == 409:
        return False
    return None


def finalize_dm(dm_id: int, body: DMFinalizeBody) -> bool:
    resp = _post(f"/discord/dms/{dm_id}/finalize/", body.model_dump(mode="json"))
    if resp is not None and resp.status_code == 200:
        return True
    log.error(
        "dm_ledger_finalize_rejected",
        **_LOG,
        ledger_id=dm_id,
        status=body.status,
        http_status_code=None if resp is None else resp.status_code,
    )
    return False


def record_dm_click(discord_message_id: str, discord_user_id: str) -> None:
    try:
        body = DMClickBody(
            discord_message_id=discord_message_id, discord_user_id=discord_user_id
        )
        resp = transport.post("/discord/dms/click/", body.model_dump(mode="json"))
    except Exception:
        log.warning("dm_click_record_failed", **_LOG, exc_info=True)
        return
    if resp is None or resp.status_code != 204:
        log.warning(
            "dm_click_record_failed",
            **_LOG,
            http_status_code=None if resp is None else resp.status_code,
        )
