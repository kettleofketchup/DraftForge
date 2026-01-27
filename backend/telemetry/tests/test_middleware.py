"""Tests for telemetry middleware."""

import uuid
from unittest import mock

import structlog
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

        # Response should have X-Request-ID header
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

        # Track what context was bound
        bound_context = {}

        def capture_response(req):
            # Capture context during request
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        # Verify context was bound
        self.assertIn("request.id", bound_context)
        self.assertEqual(bound_context["labels"], ["tournament"])
        self.assertEqual(bound_context["tournament.id"], 5)

    def test_clears_context_after_request(self):
        """Middleware clears context after request completes."""
        request = self.factory.get("/api/tournaments/5/")

        self.middleware(request)

        # Context should be cleared
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

        # user.id should not be present for anonymous users
        self.assertNotIn("user.id", bound_context)
