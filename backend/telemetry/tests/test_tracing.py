"""Tests for OpenTelemetry tracing configuration."""

import os
from unittest import TestCase, mock

from telemetry.tracing import init_tracing


class InitTracingTest(TestCase):
    """Tests for init_tracing function."""

    def setUp(self):
        """Reset tracing state before each test."""
        from telemetry import tracing

        tracing._initialized = False

    def tearDown(self):
        """Reset tracing state after each test."""
        from telemetry import tracing

        tracing._initialized = False

    def test_disabled_when_otel_enabled_false(self):
        """Tracing is no-op when OTEL_ENABLED is false."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            # Should not raise
            init_tracing()

    def test_disabled_when_no_endpoint(self):
        """Tracing is no-op when no OTLP endpoint configured."""
        env = {"OTEL_ENABLED": "true"}
        with mock.patch.dict(os.environ, env, clear=False):
            # Remove endpoint if it exists
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            # Should not raise
            init_tracing()

    def test_idempotent(self):
        """Tracing can be initialized multiple times safely."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            # Should not raise on multiple calls
            init_tracing()
            init_tracing()
            init_tracing()
