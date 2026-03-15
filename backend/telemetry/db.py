"""Django middleware for per-request database query stats logging."""

import os
from typing import Callable

from django.db import connection, reset_queries
from django.http import HttpRequest, HttpResponse

from telemetry.config import env_bool
from telemetry.logging import get_logger

log = get_logger(__name__)


def _get_slow_threshold_ms() -> float:
    """Get slow query threshold in milliseconds from env var."""
    return float(os.environ.get("SLOW_QUERY_THRESHOLD_MS", "50"))


class QueryStatsMiddleware:
    """
    Middleware that logs per-request database query statistics.

    Active by default regardless of OTEL_ENABLED -- provides continuous
    query metrics through structlog for monitoring SQLite performance.
    Disable via DB_QUERY_STATS_ENABLED=false for high-throughput scenarios.

    Logs:
    - db_query_stats: query count and total time per request
    - slow_query: individual queries exceeding SLOW_QUERY_THRESHOLD_MS (default: 50ms)

    Uses force_debug_cursor per-request to capture query timing with DEBUG=False.
    This has a small overhead (Django records SQL strings in memory per request).
    Mitigated by reset_queries() clearing the buffer each request.

    Note: Queries served from cacheops (Redis) don't appear in connection.queries,
    so this middleware measures actual SQLite load, not cached data.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        self.enabled = env_bool("DB_QUERY_STATS_ENABLED", True)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not self.enabled:
            return self.get_response(request)

        # Enable query logging for this request (works even with DEBUG=False)
        force_debug = not connection.force_debug_cursor
        if force_debug:
            connection.force_debug_cursor = True

        # Reset query log for accurate per-request counts
        reset_queries()

        try:
            response = self.get_response(request)
        finally:
            try:
                self._log_query_stats(request)
            except Exception:
                pass  # Never break the response for logging failures
            if force_debug:
                connection.force_debug_cursor = False

        return response

    def _log_query_stats(self, request: HttpRequest) -> None:
        """Log query count, total time, and any slow queries."""
        queries = connection.queries
        if not queries:
            log.info(
                "db_query_stats",
                **{
                    "db.query_count": 0,
                    "db.total_time_ms": 0.0,
                    "http.route": request.path,
                },
            )
            return

        threshold_ms = _get_slow_threshold_ms()
        total_time_ms = 0.0

        for query in queries:
            # Django reports time in seconds as a string
            query_time_ms = float(query.get("time", 0)) * 1000
            total_time_ms += query_time_ms

            if query_time_ms >= threshold_ms:
                log.warning(
                    "slow_query",
                    **{
                        "db.sql": query.get("sql", ""),
                        "db.query_time_ms": round(query_time_ms, 2),
                        "db.threshold_ms": threshold_ms,
                        "http.route": request.path,
                    },
                )

        log.info(
            "db_query_stats",
            **{
                "db.query_count": len(queries),
                "db.total_time_ms": round(total_time_ms, 2),
                "http.route": request.path,
            },
        )
