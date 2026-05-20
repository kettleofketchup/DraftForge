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

        # Severity ladder.
        #
        # * 5xx → error (always alarming).
        # * 4xx ≠ 404 → warning (auth, validation, etc.).
        # * 404 from a route that no view matched (DRF's APIRootView fallback,
        #   or no view at all) → info. These are dominated by unauthenticated
        #   scanner probes (`/api/.env`, `/api/wp-admin`) and aren't actionable.
        # * 404 from a real application view (e.g. `TournamentDetail` couldn't
        #   find pk=99999) → warning. That's a real signal — stale frontend
        #   link, lookup race, deleted resource still referenced somewhere.
        status = response.status_code
        if status >= 500:
            log_fn = log.error
        elif status == 404:
            view_module = view.__class__.__module__ if view else ""
            if not view or view_module.startswith("rest_framework."):
                log_fn = log.info
            else:
                log_fn = log.warning
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
