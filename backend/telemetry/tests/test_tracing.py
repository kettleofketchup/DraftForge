"""Tests for OpenTelemetry tracing and log export configuration."""

import os
from unittest import TestCase, mock

from telemetry.tracing import init_log_export, init_tracing


class InitTracingTest(TestCase):
    """Tests for init_tracing function."""

    def setUp(self):
        from telemetry import tracing

        tracing._tracing_initialized = False

    def tearDown(self):
        from telemetry import tracing

        tracing._tracing_initialized = False

    def test_disabled_when_otel_enabled_false(self):
        """Tracing is no-op when OTEL_ENABLED is false."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            init_tracing()

    def test_disabled_when_no_endpoint(self):
        """Tracing is no-op when no OTLP endpoint configured."""
        env = {"OTEL_ENABLED": "true"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            init_tracing()

    def test_idempotent(self):
        """Tracing can be initialized multiple times safely."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            init_tracing()
            init_tracing()
            init_tracing()


class InitLogExportTest(TestCase):
    """Tests for init_log_export function."""

    def setUp(self):
        from telemetry import tracing

        tracing._log_export_initialized = False
        tracing._log_provider = None

    def tearDown(self):
        from telemetry import tracing

        tracing._log_export_initialized = False
        tracing._log_provider = None

    def test_returns_none_when_disabled(self):
        """Log export returns None when OTEL_ENABLED is false."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            result = init_log_export()
            self.assertIsNone(result)

    def test_returns_none_when_no_endpoint(self):
        """Log export returns None when no endpoint configured."""
        env = {"OTEL_ENABLED": "true"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            result = init_log_export()
            self.assertIsNone(result)

    def test_idempotent(self):
        """Log export can be initialized multiple times safely."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            init_log_export()
            init_log_export()
            init_log_export()
