"""Operations notices: emit and resolve through the internal ops-notices API."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from app.internal_client import transport

OPS_NOTICES_PATH = "/ops-notices/"


class OpsNoticeTransientError(Exception):
    """Network error or 5xx (including database_error/event_conflict); retry with
    the same emit_id. Replay only matches the latest emit on a notice, so a retry
    that lands after another emit to that notice counts as a new occurrence."""


def _post_notice(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    resp = transport.post(path, body)
    if resp is None or resp.status_code >= 500:
        raise OpsNoticeTransientError(path)
    if not resp.ok:
        return None
    try:
        return resp.json()
    except ValueError:
        transport.log.error(
            "ops_notice_invalid_json", http_path=path, **transport.LOG_BASE
        )
        return None


def emit_ops_notice(
    key: str,
    payload: BaseModel | Mapping[str, Any],
    *,
    organization_id: int,
    event_id: int | None = None,
    event_name: str | None = None,
    event_repeater_id: int | None = None,
    subject_user_id: int | None = None,
    actor_id: int | None = None,
    dedupe_key: str | None = None,
    severity: str | None = None,
    emit_id: UUID | None = None,
) -> int | None:
    optional: dict[str, Any] = {
        "event_id": event_id,
        "event_name": event_name,
        "event_repeater_id": event_repeater_id,
        "subject_user_id": subject_user_id,
        "actor_id": actor_id,
        "dedupe_key": dedupe_key,
        "severity": severity,
        "emit_id": str(emit_id) if emit_id is not None else None,
    }
    body: dict[str, Any] = {
        "key": key,
        "payload": to_jsonable_python(
            payload if isinstance(payload, BaseModel) else dict(payload)
        ),
        "organization_id": organization_id,
        **{name: value for name, value in optional.items() if value is not None},
    }
    data = _post_notice(OPS_NOTICES_PATH, body)
    return data["id"] if data is not None else None


def resolve_ops_notice(
    key: str,
    dedupe_key: str,
    *,
    organization_id: int,
    event_id: int | None = None,
    reason: str,
) -> bool:
    body: dict[str, Any] = {
        "key": key,
        "dedupe_key": dedupe_key,
        "organization_id": organization_id,
        "reason": reason,
    }
    if event_id is not None:
        body["event_id"] = event_id
    data = _post_notice(f"{OPS_NOTICES_PATH}resolve/", body)
    return bool(data["resolved"]) if data is not None else False
