"""Failure envelope for the integration routes.

Every failure from an integration view has this shape and nothing else:

    {"error": {"code": "invalid_request", "message": "Invalid request.",
               "request_id": "<opaque>"}}

The same request ID is sent in the ``X-Request-ID`` header and logged. It
correlates logs only; it is not an idempotency key. Messages are fixed text
for the code, optionally naming a field path, and never repeat request
values, SQL, token fragments or identities. Legacy routes such as MMR sync
keep DRF's usual error shape: only views built on
``org.integration.base.IntegrationAPIView`` use this handler.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response

from telemetry.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MESSAGES: dict[str, str] = {
    "invalid_request": "Invalid request.",
    "invalid_cursor": "Invalid cursor.",
    "unauthorized": "Missing, invalid or revoked credential.",
    "forbidden": "Not allowed.",
    "feature_locked": "This feature is not enabled for this organization.",
    "not_permitted": "The token owner does not have permission for this action.",
    "operation_not_granted": "This token is not granted this operation.",
    "binding_missing": "No promotion sync binding is configured for this resource.",
    "binding_mismatch": "The configured binding does not match this organization.",
    "not_found": "Not found.",
    "method_not_allowed": "Method not allowed.",
    "not_acceptable": "Not acceptable.",
    "mapping_changed": "The mapping changed; restart the read.",
    "request_too_large": "Request body too large.",
    "unsupported_media_type": "Content type must be application/json.",
    "rate_limited": "Request limit exceeded.",
    "internal_error": "Internal error.",
}
_FORBIDDEN_CODES = frozenset(
    {"feature_locked", "not_permitted", "operation_not_granted"}
)


class IntegrationError(exceptions.APIException):
    """A contract failure with a stable ``code`` and HTTP ``status``.

    ``message`` overrides the fixed text for the code. It must not contain
    request values; a field path such as ``entries[3].recorded_at`` is fine.
    """

    def __init__(self, code: str, status: int, message: str | None = None) -> None:
        self.code = code
        self.status_code = status
        self.message = message or _DEFAULT_MESSAGES.get(code, "Request failed.")
        super().__init__(detail=self.message, code=code)


def invalid(path: str, problem: str) -> IntegrationError:
    """A 400 naming the field path and what is wrong, never the value."""
    where = path or "body"
    return IntegrationError(
        "invalid_request", 400, f"Invalid request: {where} {problem}."
    )


def _classify(exc: Exception) -> tuple[str, int, str | None]:
    if isinstance(exc, IntegrationError):
        return exc.code, exc.status_code, exc.message
    if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        return "unauthorized", exc.status_code, None
    if isinstance(exc, Http404 | exceptions.NotFound):
        return "not_found", 404, None
    if isinstance(exc, DjangoPermissionDenied):
        return "forbidden", 403, None
    if isinstance(exc, exceptions.PermissionDenied):
        detail = exc.detail
        code = detail.get("code") if isinstance(detail, dict) else None
        return (str(code) if code in _FORBIDDEN_CODES else "forbidden"), 403, None
    if isinstance(exc, exceptions.Throttled):
        return "rate_limited", 429, None
    if isinstance(exc, exceptions.UnsupportedMediaType):
        return "unsupported_media_type", 415, None
    if isinstance(exc, exceptions.MethodNotAllowed):
        return "method_not_allowed", 405, None
    if isinstance(exc, exceptions.NotAcceptable):
        return "not_acceptable", 406, None
    if isinstance(exc, exceptions.ParseError | exceptions.ValidationError):
        return "invalid_request", 400, None
    if isinstance(exc, exceptions.APIException):
        return (
            "invalid_request" if exc.status_code == 400 else "error",
            exc.status_code,
            None,
        )
    return "internal_error", 500, None


def _request_id() -> str:
    """The ID ``telemetry.middleware`` bound for this request and will send
    as ``X-Request-ID``, so the envelope, header and logs agree."""
    bound = structlog.contextvars.get_contextvars().get("request.id")
    return bound if isinstance(bound, str) and bound else str(uuid.uuid4())


def integration_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    code, status, message = _classify(exc)
    request_id = _request_id()
    view = context.get("view")
    fields = {
        "system": "org",
        "subsystem": "integration",
        "code": code,
        "status": status,
        "view": type(view).__name__ if view is not None else None,
    }
    if status >= 500:
        log.exception("integration_request_failed", **fields)
    else:
        log.info("integration_request_rejected", **fields)

    headers: dict[str, str] = {"X-Request-ID": request_id}
    auth_header = getattr(exc, "auth_header", None)
    if auth_header:
        headers["WWW-Authenticate"] = auth_header
    wait = getattr(exc, "wait", None)
    if isinstance(exc, exceptions.Throttled) and wait is not None:
        headers["Retry-After"] = str(int(wait))
    body = {
        "error": {
            "code": code,
            "message": message or _DEFAULT_MESSAGES.get(code, "Request failed."),
            "request_id": request_id,
        }
    }
    return Response(body, status=status, headers=headers)
