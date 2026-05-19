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

        # Severity ladder. 404s are dominated by unauthenticated bot probes
        # (`/api/.env`, `/api/wp-admin`, etc.) which aren't actionable
        # signal — log at info so they don't pollute the warn/error
        # dashboard. 5xx always errors. Everything else warns.
        status = response.status_code
        if status == 404:
            log_fn = log.info
        elif status >= 500:
            log_fn = log.error
        else:
            log_fn = log.warning

        log_fn(
            "drf_error_response",
            system="api",
            subsystem="drf",
            **{
                "http.status_code": status,
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
