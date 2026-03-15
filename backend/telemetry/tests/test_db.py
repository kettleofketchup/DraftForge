"""Tests for database query stats middleware."""

import os
from unittest import mock

from django.db import connection, reset_queries
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from telemetry.db import QueryStatsMiddleware


@override_settings(DEBUG=True)
class QueryStatsMiddlewareTest(TestCase):
    """Tests for QueryStatsMiddleware."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = mock.Mock(return_value=HttpResponse("OK"))
        self.middleware = QueryStatsMiddleware(self.get_response)
        reset_queries()

    def test_logs_query_stats(self):
        """Middleware logs query count and total time."""

        def handler_with_query(request):
            from django.contrib.auth import get_user_model

            User = get_user_model()
            list(User.objects.all()[:1])
            return HttpResponse("OK")

        middleware = QueryStatsMiddleware(handler_with_query)
        request = self.factory.get("/api/tournaments/")

        with mock.patch("telemetry.db.log") as mock_log:
            middleware(request)

        mock_log.info.assert_called()
        call_args = mock_log.info.call_args
        self.assertEqual(call_args[0][0], "db_query_stats")
        self.assertIn("db.query_count", call_args[1])
        self.assertIn("db.total_time_ms", call_args[1])
        self.assertGreaterEqual(call_args[1]["db.query_count"], 1)

    def test_logs_slow_queries(self):
        """Middleware logs individual queries exceeding threshold."""

        def handler_with_query(request):
            from django.contrib.auth import get_user_model

            User = get_user_model()
            list(User.objects.all()[:1])
            return HttpResponse("OK")

        middleware = QueryStatsMiddleware(handler_with_query)
        request = self.factory.get("/api/tournaments/")

        with (
            mock.patch.dict(os.environ, {"SLOW_QUERY_THRESHOLD_MS": "0"}),
            mock.patch("telemetry.db.log") as mock_log,
        ):
            middleware(request)

        warning_calls = [
            c for c in mock_log.warning.call_args_list if c[0][0] == "slow_query"
        ]
        self.assertGreaterEqual(len(warning_calls), 1)
        self.assertIn("db.query_time_ms", warning_calls[0][1])
        self.assertIn("db.sql", warning_calls[0][1])

    def test_no_slow_query_logs_under_threshold(self):
        """Middleware does not log slow queries when all are fast."""

        def handler_with_query(request):
            from django.contrib.auth import get_user_model

            User = get_user_model()
            list(User.objects.all()[:1])
            return HttpResponse("OK")

        middleware = QueryStatsMiddleware(handler_with_query)
        request = self.factory.get("/api/tournaments/")

        with (
            mock.patch.dict(os.environ, {"SLOW_QUERY_THRESHOLD_MS": "99999"}),
            mock.patch("telemetry.db.log") as mock_log,
        ):
            middleware(request)

        warning_calls = [
            c for c in mock_log.warning.call_args_list if c[0][0] == "slow_query"
        ]
        self.assertEqual(len(warning_calls), 0)

    def test_still_returns_response_on_error(self):
        """Middleware returns response even if query logging fails."""
        request = self.factory.get("/api/tournaments/")

        with mock.patch("telemetry.db.connection") as mock_conn:
            mock_conn.queries = None
            response = self.middleware(request)

        self.assertEqual(response.status_code, 200)

    def test_resets_queries_before_request(self):
        """Middleware resets query log before processing so counts are per-request."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        list(User.objects.all()[:1])
        initial_count = len(connection.queries)
        self.assertGreaterEqual(initial_count, 1)

        def handler_no_queries(request):
            return HttpResponse("OK")

        middleware = QueryStatsMiddleware(handler_no_queries)
        request = self.factory.get("/api/test/")

        with mock.patch("telemetry.db.log") as mock_log:
            middleware(request)

        call_args = mock_log.info.call_args
        self.assertEqual(call_args[1]["db.query_count"], 0)

    def test_disabled_via_env_var(self):
        """Middleware is a no-op when DB_QUERY_STATS_ENABLED=false."""
        with mock.patch.dict(os.environ, {"DB_QUERY_STATS_ENABLED": "false"}):
            middleware = QueryStatsMiddleware(self.get_response)

        request = self.factory.get("/api/tournaments/")

        with mock.patch("telemetry.db.log") as mock_log:
            response = middleware(request)

        self.assertEqual(response.status_code, 200)
        mock_log.info.assert_not_called()
