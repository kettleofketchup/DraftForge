"""The Celery/REST DM choke point: every non-gateway Discord DM goes through ``send_dm``.

No ORM here (Celery workers have no database); the ledger is reached over the
internal API through ``discordbot.internal_client.dm_ledger``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

import requests
from celery import Task, current_task
from django.conf import settings

from discordbot.dm_ledger import PERMANENT_DM_ERROR_CODES, ErrorClass
from discordbot.internal_client.dm_ledger import claim_dm, finalize_dm, mark_dm_sending
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import DMClaimBody, DMFinalizeBody
from discordbot.utils import (
    DISCORD_API_BASE,
    DiscordAuthError,
    DiscordRateLimitTimeout,
    JSONDict,
    _get_headers,
    _rate_limited_request,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

V2_FLAG: int = 1 << 15
ERROR_MAX_LEN = 300
_LOG = {"system": "discord", "subsystem": "dm"}


@dataclass(frozen=True, slots=True)
class DMRequest:
    kind: DMKind
    idempotency_key: str
    discord_user_id: str | None
    recipient_user_id: int | None = None
    organization_id: int | None = None
    subject: tuple[DMSubject, int] | None = None
    tournament_log_id: int | None = None
    context: Mapping[str, object] = field(default_factory=dict)
    content: str | None = None
    embed: JSONDict | None = None
    components: list[JSONDict] | None = None
    flags: int | None = None
    skip_status: DMStatus | None = None


@dataclass(frozen=True, slots=True)
class DMOutcome:
    status: DMStatus | Literal["duplicate", "ledger_unavailable"]
    ledger_id: int | None
    message_id: str | None
    channel_id: str | None
    error_code: int | None


OnClaimed = Callable[[int, DMStatus], None]

SKIP_STATUSES: frozenset[DMStatus] = frozenset(
    {
        DMStatus.SKIPPED_TEST_MODE,
        DMStatus.SKIPPED_NO_DISCORD,
        DMStatus.SKIPPED_DISABLED,
    }
)

DELIVERED_OUTCOMES: frozenset[DMStatus | Literal["duplicate", "ledger_unavailable"]] = (
    frozenset({DMStatus.SENT, DMStatus.SKIPPED_TEST_MODE, "duplicate"})
)


def task_run_id(task: Task) -> str:
    return str(task.request.id or "local")


class _PayloadError(Exception):
    pass


@dataclass(slots=True)
class _SendState:
    ledger_id: int
    claim_token: str
    finalized: bool = False
    marked: bool = False


def _claim_token() -> str:
    task_id = getattr(getattr(current_task, "request", None), "id", None)
    return f"{task_id or 'local'}:{uuid4().hex[:8]}"


def _parse_discord_error(exc: BaseException) -> tuple[int | None, int | None, str]:
    response = getattr(exc, "response", None)
    http_status: int | None = None
    code: int | None = None
    message = str(exc)
    if isinstance(response, requests.Response):
        http_status = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            raw_code = body.get("code")
            if isinstance(raw_code, int) and not isinstance(raw_code, bool):
                code = raw_code
            raw_message = body.get("message")
            if isinstance(raw_message, str) and raw_message:
                message = raw_message
    return http_status, code, message[:ERROR_MAX_LEN]


def _open_dm_channel(discord_user_id: str) -> str:
    response = _rate_limited_request(
        "POST",
        f"{DISCORD_API_BASE}/users/@me/channels",
        json={"recipient_id": discord_user_id},
        headers=_get_headers(),
    )
    response.raise_for_status()
    channel_id = response.json().get("id")
    if not channel_id:
        raise ValueError("DM channel response has no id")
    return str(channel_id)


def _build_payload(req: DMRequest, ledger_id: int) -> JSONDict:
    is_v2 = bool(req.flags and req.flags & V2_FLAG)
    if is_v2 and (req.content or req.embed):
        raise _PayloadError("v2_with_content")
    payload: JSONDict = {}
    if req.content:
        payload["content"] = req.content
    if req.embed:
        payload["embeds"] = [req.embed]
    if req.components:
        payload["components"] = req.components
    if not payload:
        raise _PayloadError("empty_payload")
    if req.flags is not None:
        payload["flags"] = req.flags
    payload["nonce"] = f"dm{ledger_id}"
    payload["enforce_nonce"] = True
    return payload


def _test_mode_skips(discord_user_id: str) -> bool:
    if not getattr(settings, "TEST", False):
        return False
    target = str(getattr(settings, "TEST_DISCORD_USER_ID", "") or "")
    return not target or discord_user_id != target


def _claim_body(
    req: DMRequest, token: str, initial_status: DMStatus | None
) -> DMClaimBody:
    subject_type, subject_id = req.subject if req.subject else (None, None)
    return DMClaimBody(
        kind=req.kind.value,
        idempotency_key=req.idempotency_key,
        claim_token=token,
        discord_user_id=req.discord_user_id or "",
        recipient_user_id=req.recipient_user_id,
        organization_id=req.organization_id,
        subject_type=subject_type.value if subject_type else None,
        subject_id=subject_id,
        tournament_log_id=req.tournament_log_id,
        context=dict(req.context),
        has_components=bool(req.components),
        initial_status=initial_status.value if initial_status else None,
    )


def _outcome(
    status: DMStatus | Literal["duplicate", "ledger_unavailable"],
    ledger_id: int | None,
    *,
    message_id: str | None = None,
    channel_id: str | None = None,
    error_code: int | None = None,
) -> DMOutcome:
    return DMOutcome(
        status=status,
        ledger_id=ledger_id,
        message_id=message_id,
        channel_id=channel_id,
        error_code=error_code,
    )


def _run_hook(on_claimed: OnClaimed | None, ledger_id: int, status: DMStatus) -> None:
    if on_claimed is not None:
        on_claimed(ledger_id, status)


def _record_skip(
    req: DMRequest,
    token: str,
    status: DMStatus,
    on_claimed: OnClaimed | None,
) -> DMOutcome:
    claim = claim_dm(_claim_body(req, token, status))
    if claim is None:
        log.error(
            "dm_ledger_unavailable",
            **_LOG,
            dm_kind=req.kind.value,
            discord_user_id=req.discord_user_id,
            status=status.value,
        )
        return _outcome("ledger_unavailable", None)
    if not claim.granted:
        log.info(
            "dm_duplicate_suppressed",
            **_LOG,
            dm_kind=req.kind.value,
            ledger_id=claim.id,
            discord_user_id=req.discord_user_id,
            status=claim.status.value,
        )
        return _outcome("duplicate", claim.id)
    if status == DMStatus.SKIPPED_TEST_MODE:
        log.info(
            "dm_skipped_test_mode",
            **_LOG,
            dm_kind=req.kind.value,
            ledger_id=claim.id,
            discord_user_id=req.discord_user_id,
            status=status.value,
        )
    try:
        _run_hook(on_claimed, claim.id, status)
    except Exception:
        log.error(
            "dm_on_claimed_failed",
            **_LOG,
            dm_kind=req.kind.value,
            ledger_id=claim.id,
            discord_user_id=req.discord_user_id,
            status=status.value,
            exc_info=True,
        )
    return _outcome(status, claim.id)


def _finalize(
    req: DMRequest,
    state: _SendState,
    status: DMStatus,
    *,
    error_class: ErrorClass | None = None,
    channel_id: str = "",
    message_id: str | None = None,
    http_status: int | None = None,
    error_code: int | None = None,
    error: str = "",
) -> DMOutcome:
    state.finalized = True
    body = DMFinalizeBody(
        claim_token=state.claim_token,
        status=status.value,
        error_class=error_class,
        discord_channel_id=channel_id,
        discord_message_id=message_id,
        http_status=http_status,
        error_code=error_code,
        error=error[:ERROR_MAX_LEN],
    )
    fields = {
        **_LOG,
        "dm_kind": req.kind.value,
        "ledger_id": state.ledger_id,
        "discord_user_id": req.discord_user_id,
        "status": status.value,
    }
    if status == DMStatus.SENT:
        log.info("dm_sent", **fields)
    else:
        log.warning(
            "dm_failed",
            **fields,
            error_class=error_class,
            error_code=error_code,
            http_status_code=http_status,
            error=error[:ERROR_MAX_LEN],
        )
    if not finalize_dm(state.ledger_id, body):
        log.error("dm_ledger_finalize_failed", **fields)
    return _outcome(
        status,
        state.ledger_id,
        message_id=message_id,
        channel_id=channel_id or None,
        error_code=error_code,
    )


def _channel_failure(req: DMRequest, state: _SendState, exc: Exception) -> DMOutcome:
    http_status, code, message = _parse_discord_error(exc)
    error_class: ErrorClass = (
        "permanent" if code in PERMANENT_DM_ERROR_CODES else "pre_send"
    )
    return _finalize(
        req,
        state,
        DMStatus.FAILED,
        error_class=error_class,
        http_status=http_status,
        error_code=code,
        error=message,
    )


def _post_failure(
    req: DMRequest, state: _SendState, channel_id: str, exc: Exception
) -> DMOutcome:
    http_status, code, message = _parse_discord_error(exc)
    status = DMStatus.UNKNOWN
    error_class: ErrorClass | None = None
    if isinstance(exc, DiscordAuthError):
        status, error_class = DMStatus.FAILED, "pre_send"
    elif isinstance(exc, DiscordRateLimitTimeout) or http_status == 429:
        status, error_class = DMStatus.FAILED, "rate_limit_timeout"
    elif isinstance(exc, requests.ConnectTimeout):
        status, error_class = DMStatus.FAILED, "pre_send"
    elif (
        isinstance(exc, requests.HTTPError)
        and http_status is not None
        and 400 <= http_status < 500
    ):
        status = DMStatus.FAILED
        error_class = "permanent" if code in PERMANENT_DM_ERROR_CODES else "pre_send"
    return _finalize(
        req,
        state,
        status,
        error_class=error_class,
        channel_id=channel_id,
        http_status=http_status,
        error_code=code,
        error=message,
    )


def _deliver(
    req: DMRequest, state: _SendState, on_claimed: OnClaimed | None
) -> DMOutcome:
    discord_user_id = req.discord_user_id or ""
    try:
        try:
            _run_hook(on_claimed, state.ledger_id, DMStatus.PENDING)
        except Exception as exc:
            log.error(
                "dm_on_claimed_failed",
                **_LOG,
                dm_kind=req.kind.value,
                ledger_id=state.ledger_id,
                discord_user_id=discord_user_id,
                status=DMStatus.PENDING.value,
                exc_info=True,
            )
            return _finalize(
                req,
                state,
                DMStatus.FAILED,
                error_class="before_send_failed",
                error=str(exc),
            )

        try:
            channel_id = _open_dm_channel(discord_user_id)
        except Exception as exc:
            outcome = _channel_failure(req, state, exc)
            if isinstance(exc, DiscordAuthError):
                raise
            return outcome

        try:
            payload = _build_payload(req, state.ledger_id)
        except _PayloadError as exc:
            return _finalize(
                req,
                state,
                DMStatus.FAILED,
                error_class="permanent",
                channel_id=channel_id,
                error=str(exc),
            )

        try:
            marked = mark_dm_sending(state.ledger_id, claim_token=state.claim_token)
        except Exception as exc:
            return _finalize(
                req,
                state,
                DMStatus.FAILED,
                error_class="pre_send",
                channel_id=channel_id,
                error=f"mark_sending_error: {exc}",
            )
        if not marked:
            return _finalize(
                req,
                state,
                DMStatus.FAILED,
                error_class="pre_send",
                channel_id=channel_id,
                error="mark_sending_refused"
                if marked is False
                else "mark_sending_unavailable",
            )
        state.marked = True

        try:
            response = _rate_limited_request(
                "POST",
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                json=payload,
                headers=_get_headers(),
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            outcome = _post_failure(req, state, channel_id, exc)
            if isinstance(exc, DiscordAuthError):
                raise
            return outcome

        message_id = data.get("id") if isinstance(data, dict) else None
        return _finalize(
            req,
            state,
            DMStatus.SENT,
            channel_id=channel_id,
            message_id=str(message_id) if message_id else None,
            http_status=response.status_code,
        )
    finally:
        if not state.finalized:
            if state.marked:
                _finalize(
                    req, state, DMStatus.UNKNOWN, error="interrupted_after_send_start"
                )
            else:
                _finalize(
                    req,
                    state,
                    DMStatus.FAILED,
                    error_class="pre_send",
                    error="interrupted_before_send",
                )


def send_dm(req: DMRequest, *, on_claimed: OnClaimed | None = None) -> DMOutcome:
    if req.skip_status is not None and req.skip_status not in SKIP_STATUSES:
        raise ValueError(f"skip_status must be a skip status, not {req.skip_status}")
    token = _claim_token()
    if req.skip_status is not None:
        return _record_skip(req, token, req.skip_status, on_claimed)
    if not req.discord_user_id:
        return _record_skip(req, token, DMStatus.SKIPPED_NO_DISCORD, on_claimed)
    if _test_mode_skips(req.discord_user_id):
        return _record_skip(req, token, DMStatus.SKIPPED_TEST_MODE, on_claimed)

    claim = claim_dm(_claim_body(req, token, None))
    if claim is None:
        log.error(
            "dm_ledger_unavailable",
            **_LOG,
            dm_kind=req.kind.value,
            discord_user_id=req.discord_user_id,
            status="ledger_unavailable",
        )
        return _outcome("ledger_unavailable", None)
    if not claim.granted:
        log.info(
            "dm_duplicate_suppressed",
            **_LOG,
            dm_kind=req.kind.value,
            ledger_id=claim.id,
            discord_user_id=req.discord_user_id,
            status=claim.status.value,
        )
        return _outcome("duplicate", claim.id)

    return _deliver(req, _SendState(ledger_id=claim.id, claim_token=token), on_claimed)
