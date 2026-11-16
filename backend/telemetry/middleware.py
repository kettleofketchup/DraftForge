"""Django middleware for telemetry context binding."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.http import HttpRequest, HttpResponse

from telemetry.labels import extract_labels
from telemetry.logging import get_logger

_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")

log = get_logger(__name__)


def _authenticated_user_id(request: HttpRequest) -> Any | None:
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user.pk
    return None


class TelemetryMiddleware:
    """
    Middleware that binds telemetry context to each request.

    Responsibilities:
    - Generate or accept request_id (from X-Request-ID header)
    - Extract user_id from authenticated session
    - Extract labels from URL path
    - Bind all context to structlog for request duration
    - Add X-Request-ID to response headers
    - Log request completion with timing

    Sync and async capable so an ASGI request chain needs no async_to_sync hop.
    """

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse]
        | Callable[[HttpRequest], Awaitable[HttpResponse]],
    ) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if self.is_async:
            return self.__acall__(request)

        start_time = time.perf_counter()
        request_id = self._bind_context(request, _authenticated_user_id(request))
        try:
            response = self.get_response(request)
            return self._complete(request, response, request_id, start_time)
        except Exception as e:
            self._log_failed(request, e, start_time)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        start_time = time.perf_counter()
        # request.user is a sync lazy object; resolve it on the request's sync thread
        # so the views reuse the same cached user.
        user_id = await sync_to_async(_authenticated_user_id, thread_sensitive=True)(
            request
        )
        request_id = self._bind_context(request, user_id)
        try:
            response = await self.get_response(request)
            return self._complete(request, response, request_id, start_time)
        except Exception as e:
            self._log_failed(request, e, start_time)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    @staticmethod
    def _bind_context(request: HttpRequest, user_id: Any | None) -> str:
        client_id = request.headers.get("X-Request-ID", "")
        request_id = (
            client_id
            if client_id and _REQUEST_ID_RE.match(client_id)
            else str(uuid.uuid4())
        )
        context: dict[str, Any] = {
            "request.id": request_id,
            **extract_labels(request.path),
        }
        if user_id is not None:
            context["user.id"] = user_id
        structlog.contextvars.bind_contextvars(**context)
        return request_id

    @staticmethod
    def _complete(
        request: HttpRequest,
        response: HttpResponse,
        request_id: str,
        start_time: float,
    ) -> HttpResponse:
        duration_ms = (time.perf_counter() - start_time) * 1000
        log.info(
            "request_completed",
            **{
                "http.method": request.method,
                "http.route": request.path,
                "http.status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        response["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _log_failed(request: HttpRequest, error: Exception, start_time: float) -> None:
        duration_ms = (time.perf_counter() - start_time) * 1000
        log.error(
            "request_failed",
            **{
                "http.method": request.method,
                "http.route": request.path,
                "duration_ms": round(duration_ms, 2),
                "error": str(error),
            },
            exc_info=True,
        )
