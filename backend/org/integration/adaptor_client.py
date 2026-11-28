"""HTTP client for the adaptor's per-DM receipt intake.

``PromotionAdaptorClient.record(payload)`` POSTs one frozen outbox payload to
``{base_url}/api/v1/organizations/{org_id}/promotion/contact-receipts`` and
turns the answer into a ``ReceiptOutcome``. It never raises for an HTTP or
transport problem; every answer becomes an outcome kind the dispatcher can
act on.

Only a 200 whose body is exactly the contract's applied outcome
(``status=applied``, ``applied`` and ``durable`` true, a canonical
``contact_log_id`` and this receipt's ``delivery_id``) is ``APPLIED``. A 200
``already_contacted`` names existing external evidence, not storage of this DM. Any
other 2xx, a malformed body, a duplicate key, an extra field or a mismatched
``delivery_id`` is ``INVALID_RESPONSE``.

The body sent is the canonical JSON of the payload, so every retry of a
receipt is byte for byte the same. Redirects are never followed and proxy
settings from the environment are ignored. Logs carry the delivery UUID,
status and a fixed reason code; never the payload, a Discord or user ID, the
key or any response text.

``ConnectionReceiptClient`` sends the same bytes to an adopted stream
connection over the org-safe transport with that connection's own credential;
the deployment key is never used there.
"""

from __future__ import annotations

import email.utils
import enum
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import requests
from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import PermissionDenied

from common.strict_json import StrictJSONError, loads_strict, parse_canonical_id
from config.promotion_sync import PromotionAdaptorConfig
from org.api_connections.authority import (
    ConnectionAuthorityLost,
    assert_connection_authority,
    denial_code,
)
from org.api_connections.crypto import (
    CredentialError,
    canonical_origin,
    open_credential,
)
from org.api_connections.limits import REQUEST_SECONDS
from org.api_connections.safe_http import request_bytes
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import SafeHttpRequest
from org.integration.receipts import canonical_receipt_json
from org.models import OrgApiConnection
from telemetry.logging import get_logger

log = get_logger(__name__)

MAX_RESPONSE_BYTES: Final[int] = 256 * 1024
_PATH: Final[str] = "/api/v1/organizations/{org_id}/promotion/contact-receipts"
_NOT_APPLIED_REASONS: Final = frozenset({"writeback_disabled", "dry_run"})
_STORED_KEYS: Final = frozenset(
    {"delivery_id", "status", "applied", "durable", "contact_log_id"}
)
_NOT_APPLIED_KEYS: Final = frozenset(
    {"delivery_id", "status", "reason", "applied", "durable"}
)


class OutcomeKind(enum.StrEnum):
    APPLIED = "applied"
    ALREADY_CONTACTED = "already_contacted"
    NOT_APPLIED = "not_applied"
    MAPPING_REQUIRED = "mapping_required"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    REJECTED = "rejected"
    RETRYABLE = "retryable"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class ReceiptOutcome:
    """What the adaptor said about one receipt.

    ``reason`` is a fixed code. ``contact_log_id`` is set only for applied
    and already_contacted. ``retry_after`` is the server's Retry-After in
    seconds, when it sent a usable one.
    """

    kind: OutcomeKind
    reason: str
    http_status: int | None
    contact_log_id: int | None = None
    retry_after: float | None = None


_TRANSPORT_OUTCOMES: Final[dict[str, tuple[OutcomeKind, str]]] = {
    "deadline_exceeded": (OutcomeKind.RETRYABLE, "timeout"),
    "network_failed": (OutcomeKind.RETRYABLE, "connection_error"),
    "dns_failed": (OutcomeKind.RETRYABLE, "connection_error"),
    "unsafe_address": (OutcomeKind.NOT_APPLIED, "unsafe_destination"),
    "peer_mismatch": (OutcomeKind.NOT_APPLIED, "unsafe_destination"),
    "invalid_url": (OutcomeKind.NOT_APPLIED, "unsafe_destination"),
    "response_too_large": (OutcomeKind.INVALID_RESPONSE, "invalid_response"),
    "invalid_compression": (OutcomeKind.INVALID_RESPONSE, "invalid_response"),
    "unsupported_encoding": (OutcomeKind.INVALID_RESPONSE, "invalid_response"),
}


class _Invalid(Exception):
    pass


def _invalid(status: int) -> ReceiptOutcome:
    return ReceiptOutcome(OutcomeKind.INVALID_RESPONSE, "invalid_response", status)


class PromotionAdaptorClient:
    def __init__(self, config: PromotionAdaptorConfig) -> None:
        if not config.enabled or not config.base_url or not config.api_key:
            raise ImproperlyConfigured("promotion adaptor dispatch is not enabled")
        self._config = config
        self._session = requests.Session()
        self._session.trust_env = False

    def record(self, payload: dict[str, Any]) -> ReceiptOutcome:
        delivery_id = str(payload["delivery_id"])
        org_id = parse_canonical_id(payload["org_id"])
        if org_id is None:
            raise ValueError("payload org_id is not a canonical id")
        url = self._config.base_url + _PATH.format(org_id=org_id)
        body = canonical_receipt_json(payload).encode("utf-8")
        started = time.monotonic()
        result = self._post(url, body, delivery_id)
        log.info(
            "promo_adaptor_receipt_answered",
            system="org",
            subsystem="integration",
            org_id=org_id,
            delivery_id=delivery_id,
            http_status=result.http_status,
            outcome=result.kind.value,
            reason=result.reason or None,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return result

    def _post(self, url: str, body: bytes, delivery_id: str) -> ReceiptOutcome:
        try:
            response = self._session.post(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                },
                timeout=self._config.timeout,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout:
            return ReceiptOutcome(OutcomeKind.RETRYABLE, "timeout", None)
        except requests.ConnectionError:
            return ReceiptOutcome(OutcomeKind.RETRYABLE, "connection_error", None)
        except requests.RequestException:
            return ReceiptOutcome(OutcomeKind.RETRYABLE, "transport_error", None)
        with response:
            status = response.status_code
            try:
                raw = _read_bounded(response)
            except requests.Timeout:
                return ReceiptOutcome(OutcomeKind.RETRYABLE, "timeout", status)
            except requests.RequestException:
                return ReceiptOutcome(OutcomeKind.RETRYABLE, "connection_error", status)
            except _Invalid:
                return _invalid(status)
            return _classify(status, raw, response.headers, delivery_id)


def _held(reason: str) -> ReceiptOutcome:
    return ReceiptOutcome(OutcomeKind.NOT_APPLIED, reason, None)


class ConnectionReceiptClient:
    """Sends one frozen receipt to an adopted stream connection's destination.

    Uses the org-safe transport. Every attempt rechecks the connection's
    flags, saved version, destination and outbound authority; anything the
    adaptor contract cannot honor pauses with a fixed reason.
    """

    def record(
        self,
        payload: dict[str, Any],
        *,
        connection_id: int,
        origin: str,
        config_version: int,
    ) -> ReceiptOutcome:
        delivery_id = str(payload["delivery_id"])
        started = time.monotonic()
        result = self._record(payload, connection_id, origin, config_version)
        log.info(
            "promo_adaptor_receipt_answered",
            system="org",
            subsystem="integration",
            org_id=payload.get("org_id"),
            connection_id=connection_id,
            delivery_id=delivery_id,
            http_status=result.http_status,
            outcome=result.kind.value,
            reason=result.reason or None,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return result

    def _record(
        self,
        payload: dict[str, Any],
        connection_id: int,
        origin: str,
        config_version: int,
    ) -> ReceiptOutcome:
        connection = OrgApiConnection.objects.filter(pk=connection_id).first()
        if connection is None or connection.archived_at is not None:
            return _held("connection_archived")
        if not (connection.enabled and connection.promotion_push_enabled):
            return _held("direction_disabled")
        try:
            current = canonical_origin(connection.outbound_base_url)
        except CredentialError:
            current = ""
        if current != origin:
            return _held("origin_changed")
        if connection.config_version != config_version:
            return ReceiptOutcome(OutcomeKind.RETRYABLE, "configuration_changed", None)
        if connection.outbound_auth != "bearer":
            return _held("unsupported_auth")
        try:
            assert_connection_authority(connection, direction="promotion_push")
        except ConnectionAuthorityLost as lost:
            lost.cleanup()
            return _held("authority_lost")
        except PermissionDenied as denied:
            return _held(denial_code(denied))
        try:
            credential = open_credential(
                connection.outbound_credential_ciphertext,
                org_id=connection.organization_id,
                connection_id=connection.pk,
                origin=origin,
            )
        except CredentialError as exc:
            return _held(exc.code)
        org_id = parse_canonical_id(payload["org_id"])
        if org_id != connection.organization_id:
            raise ValueError("payload org_id does not match the connection")
        request = SafeHttpRequest(
            url=connection.outbound_base_url.rstrip("/") + _PATH.format(org_id=org_id),
            method="POST",
            body=payload,
            body_encoding="canonical",
            auth="bearer",
            credential=credential,
            credential_origin=origin,
        )
        del credential
        try:
            raw = request_bytes(
                request,
                deadline=time.monotonic() + REQUEST_SECONDS,
                max_bytes=MAX_RESPONSE_BYTES,
            )
        except SafeHttpError as exc:
            kind, reason = _TRANSPORT_OUTCOMES.get(
                exc.code, (OutcomeKind.NOT_APPLIED, exc.code)
            )
            return ReceiptOutcome(kind, reason, None)
        return _classify(
            raw.status,
            raw.body,
            {"Retry-After": raw.retry_after},
            str(payload["delivery_id"]),
        )


def _read_bounded(response: requests.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=16384):
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise _Invalid
        chunks.append(chunk)
    return b"".join(chunks)


def _classify(
    status: int, raw: bytes, headers: Any, delivery_id: str
) -> ReceiptOutcome:
    if status == 401:
        return ReceiptOutcome(OutcomeKind.UNAUTHORIZED, "adaptor_unauthorized", status)
    if status == 403:
        return ReceiptOutcome(OutcomeKind.FORBIDDEN, "adaptor_forbidden", status)
    if status in (408, 429) or status >= 500:
        reason = {
            408: "timeout",
            429: "rate_limited",
            503: "adaptor_unavailable",
        }.get(status, "server_error")
        return ReceiptOutcome(
            OutcomeKind.RETRYABLE,
            reason,
            status,
            retry_after=_retry_after(headers.get("Retry-After")),
        )
    if status == 200:
        try:
            return _stored_outcome(_object(raw), delivery_id)
        except _Invalid:
            return _invalid(status)
    if status == 409:
        try:
            return _conflict(_object(raw), delivery_id)
        except _Invalid:
            return _invalid(status)
    if 200 <= status < 300:
        return _invalid(status)
    return ReceiptOutcome(OutcomeKind.REJECTED, "adaptor_rejected", status)


def _object(raw: bytes) -> dict[str, Any]:
    try:
        value = loads_strict(raw)
    except StrictJSONError:
        raise _Invalid from None
    if not isinstance(value, dict):
        raise _Invalid
    return value


def _check_delivery(body: dict[str, Any], delivery_id: str) -> None:
    if body.get("delivery_id") != delivery_id:
        raise _Invalid


def _stored_outcome(body: dict[str, Any], delivery_id: str) -> ReceiptOutcome:
    if set(body) != _STORED_KEYS:
        raise _Invalid
    _check_delivery(body, delivery_id)
    contact_log_id = parse_canonical_id(body["contact_log_id"])
    if contact_log_id is None:
        raise _Invalid
    applied, durable = body["applied"], body["durable"]
    if body["status"] == "applied" and applied is True and durable is True:
        return ReceiptOutcome(
            OutcomeKind.APPLIED, "", 200, contact_log_id=contact_log_id
        )
    if body["status"] == "already_contacted" and applied is False and durable is False:
        return ReceiptOutcome(
            OutcomeKind.ALREADY_CONTACTED,
            "already_contacted",
            200,
            contact_log_id=contact_log_id,
        )
    raise _Invalid


def _conflict(body: dict[str, Any], delivery_id: str) -> ReceiptOutcome:
    if "error" in body:
        error = body["error"]
        code = error.get("code") if isinstance(error, dict) else None
        if code == "mapping_required":
            return ReceiptOutcome(OutcomeKind.MAPPING_REQUIRED, "mapping_required", 409)
        if code == "idempotency_conflict":
            return ReceiptOutcome(
                OutcomeKind.IDEMPOTENCY_CONFLICT, "idempotency_conflict", 409
            )
        raise _Invalid
    if set(body) != _NOT_APPLIED_KEYS:
        raise _Invalid
    _check_delivery(body, delivery_id)
    valid = (
        body["status"] == "not_applied"
        and body["reason"] in _NOT_APPLIED_REASONS
        and body["applied"] is False
        and body["durable"] is False
    )
    if not valid:
        raise _Invalid
    return ReceiptOutcome(OutcomeKind.NOT_APPLIED, body["reason"], 409)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        return float(int(value))
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None or when.tzinfo is None:
        return None
    return max(0.0, (when - datetime.now(UTC)).total_seconds())
