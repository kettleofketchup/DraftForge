"""Django middleware for telemetry context binding."""

import time
import uuid
from typing import Callable

import structlog
from django.http import HttpRequest, HttpResponse

from telemetry.labels import extract_labels
from telemetry.logging import get_logger

log = get_logger(__name__)


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
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Start timing
        start_time = time.perf_counter()

        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Extract user ID if authenticated
        user_id = None
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = request.user.pk

        # Extract labels from URL
        labels = extract_labels(request.path)

        # Build context dict
        context: dict = {
            "request.id": request_id,
            **labels,
        }
        if user_id is not None:
            context["user.id"] = user_id

        # Bind context to structlog
        structlog.contextvars.bind_contextvars(**context)

        try:
            # Process request
            response = self.get_response(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion
            log.info(
                "request_completed",
                **{
                    "http.method": request.method,
                    "http.route": request.path,
                    "http.status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

            # Add request ID to response
            response["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Log error
            duration_ms = (time.perf_counter() - start_time) * 1000
            log.error(
                "request_failed",
                **{
                    "http.method": request.method,
                    "http.route": request.path,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

        finally:
            # Always clear context
            structlog.contextvars.clear_contextvars()
