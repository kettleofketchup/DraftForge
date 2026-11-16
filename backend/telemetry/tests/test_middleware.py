"""Tests for telemetry middleware."""

import asyncio
import uuid
from unittest import mock

import structlog
from asgiref.sync import iscoroutinefunction
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from telemetry.middleware import TelemetryMiddleware


class TelemetryMiddlewareTest(TestCase):
    """Tests for TelemetryMiddleware."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.get_response = mock.Mock(return_value=HttpResponse("OK"))
        self.middleware = TelemetryMiddleware(self.get_response)
        structlog.contextvars.clear_contextvars()

    def tearDown(self):
        """Clean up after tests."""
        structlog.contextvars.clear_contextvars()

    def test_generates_request_id(self):
        """Middleware generates request_id if not provided."""
        request = self.factory.get("/api/tournaments/")

        response = self.middleware(request)

        self.assertIn("X-Request-ID", response)
        # Should be a valid UUID
        uuid.UUID(response["X-Request-ID"])

    def test_accepts_request_id_header(self):
        """Middleware accepts X-Request-ID from client."""
        request_id = "client-provided-id-123"
        request = self.factory.get(
            "/api/tournaments/",
            HTTP_X_REQUEST_ID=request_id,
        )

        response = self.middleware(request)

        self.assertEqual(response["X-Request-ID"], request_id)

    def test_binds_context_for_request(self):
        """Middleware binds context to structlog."""
        request = self.factory.get("/api/tournaments/5/")

        bound_context = {}

        def capture_response(req):
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        self.assertIn("request.id", bound_context)
        self.assertEqual(bound_context["labels"], ["tournament"])
        self.assertEqual(bound_context["tournament.id"], 5)

    def test_clears_context_after_request(self):
        """Middleware clears context after request completes."""
        request = self.factory.get("/api/tournaments/5/")

        self.middleware(request)

        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("tournament.id", ctx)

    def test_binds_user_id_when_authenticated(self):
        """Middleware binds user.id for authenticated requests."""
        request = self.factory.get("/api/tournaments/")
        request.user = mock.Mock()
        request.user.is_authenticated = True
        request.user.pk = 42

        bound_context = {}

        def capture_response(req):
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        self.assertEqual(bound_context["user.id"], 42)

    def test_handles_anonymous_user(self):
        """Middleware handles anonymous users gracefully."""
        request = self.factory.get("/api/tournaments/")
        request.user = mock.Mock()
        request.user.is_authenticated = False

        bound_context = {}

        def capture_response(req):
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        self.assertNotIn("user.id", bound_context)

    def test_rejects_invalid_request_id(self):
        """Middleware ignores invalid X-Request-ID and generates new one."""
        request = self.factory.get(
            "/api/tournaments/",
            HTTP_X_REQUEST_ID="<script>alert('xss')</script>",
        )
        response = self.middleware(request)
        # Should have generated a valid UUID, not used the malicious value
        uuid.UUID(response["X-Request-ID"])

    def test_rejects_oversized_request_id(self):
        """Middleware ignores oversized X-Request-ID."""
        request = self.factory.get(
            "/api/tournaments/",
            HTTP_X_REQUEST_ID="a" * 200,
        )
        response = self.middleware(request)
        self.assertTrue(len(response["X-Request-ID"]) <= 64)

    def test_logs_request_cancelled_and_reraises(self) -> None:
        """CancelledError is a BaseException; it must still be logged."""
        request = self.factory.get("/api/bracket/tournaments/105/")
        middleware = TelemetryMiddleware(
            mock.Mock(side_effect=asyncio.CancelledError())
        )

        with mock.patch("telemetry.middleware.log") as log:
            with self.assertRaises(asyncio.CancelledError):
                middleware(request)

        log.error.assert_not_called()
        log.info.assert_not_called()
        log.warning.assert_called_once()
        args, kwargs = log.warning.call_args
        self.assertEqual(args, ("request_cancelled",))
        self.assertEqual(kwargs["system"], "http")
        self.assertEqual(kwargs["subsystem"], "request")
        self.assertEqual(kwargs["http.method"], "GET")
        self.assertEqual(kwargs["http.route"], "/api/bracket/tournaments/105/")
        self.assertIsInstance(kwargs["duration_ms"], float)
        self.assertNotIn("tournament.id", structlog.contextvars.get_contextvars())


async def _async_ok(request):
    return HttpResponse("OK")


class TelemetryMiddlewareAsyncTest(TestCase):
    """Tests for TelemetryMiddleware on the async (ASGI) path."""

    def setUp(self):
        self.factory = RequestFactory()
        structlog.contextvars.clear_contextvars()

    def tearDown(self):
        structlog.contextvars.clear_contextvars()

    def test_async_mode_follows_get_response(self):
        self.assertTrue(iscoroutinefunction(TelemetryMiddleware(_async_ok)))
        self.assertFalse(iscoroutinefunction(TelemetryMiddleware(mock.Mock())))

    async def test_binds_context_and_sets_request_id(self):
        request = self.factory.get("/api/tournaments/5/", HTTP_X_REQUEST_ID="abc-123")
        request.user = mock.Mock(is_authenticated=True, pk=42)
        bound_context = {}

        async def capture_response(req):
            bound_context.update(structlog.contextvars.get_contextvars())
            return HttpResponse("OK")

        with mock.patch("telemetry.middleware.log") as mock_log:
            response = await TelemetryMiddleware(capture_response)(request)

        self.assertEqual(response["X-Request-ID"], "abc-123")
        self.assertEqual(bound_context["request.id"], "abc-123")
        self.assertEqual(bound_context["tournament.id"], 5)
        self.assertEqual(bound_context["user.id"], 42)
        self.assertNotIn("tournament.id", structlog.contextvars.get_contextvars())
        mock_log.info.assert_called_once()
        self.assertEqual(mock_log.info.call_args[0][0], "request_completed")
        self.assertEqual(mock_log.info.call_args[1]["http.status_code"], 200)

    async def test_logs_request_failed_and_reraises(self):
        async def boom(req):
            raise ValueError("boom")

        request = self.factory.get("/api/tournaments/")
        with mock.patch("telemetry.middleware.log") as mock_log:
            with self.assertRaises(ValueError):
                await TelemetryMiddleware(boom)(request)

        mock_log.error.assert_called_once()
        self.assertEqual(mock_log.error.call_args[0][0], "request_failed")
        self.assertEqual(mock_log.error.call_args[1]["error"], "boom")
        self.assertEqual(structlog.contextvars.get_contextvars(), {})

    async def test_logs_request_cancelled_and_reraises(self) -> None:
        async def cancelled(req: object) -> HttpResponse:
            raise asyncio.CancelledError()

        request = self.factory.get("/api/bracket/tournaments/105/")
        with mock.patch("telemetry.middleware.log") as log:
            with self.assertRaises(asyncio.CancelledError):
                await TelemetryMiddleware(cancelled)(request)

        log.error.assert_not_called()
        log.info.assert_not_called()
        log.warning.assert_called_once()
        args, kwargs = log.warning.call_args
        self.assertEqual(args, ("request_cancelled",))
        self.assertEqual(kwargs["system"], "http")
        self.assertEqual(kwargs["subsystem"], "request")
        self.assertEqual(kwargs["http.method"], "GET")
        self.assertEqual(kwargs["http.route"], "/api/bracket/tournaments/105/")
        self.assertIsInstance(kwargs["duration_ms"], float)
        self.assertNotIn("tournament.id", structlog.contextvars.get_contextvars())
