"""Custom DRF exception handler with structured logging."""

from rest_framework.views import exception_handler as drf_exception_handler

from telemetry.logging import get_logger

log = get_logger("app.exception_handler")


def exception_handler(exc, context):
    """Wrap DRF's default exception handler to log 4xx/5xx responses."""
    response = drf_exception_handler(exc, context)

    if response is not None and response.status_code >= 400:
        view = context.get("view")
        request = context.get("request")

        log_fn = log.warning if response.status_code < 500 else log.error
        log_fn(
            "drf_error_response",
            system="api",
            subsystem="drf",
            **{
                "http.status_code": response.status_code,
                "http.method": getattr(request, "method", None),
                "http.route": getattr(request, "path", None),
                "view": (
                    f"{view.__class__.__module__}.{view.__class__.__qualname__}"
                    if view
                    else None
                ),
                "errors": response.data,
            },
        )

    return response
