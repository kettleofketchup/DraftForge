"""Tests for OpenTelemetry tracing and log export configuration."""

import os
import sqlite3
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import TestCase, mock

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

from telemetry import tracing
from telemetry.tracing import init_log_export, init_tracing


def _otel_globals() -> dict[str, Any]:
    return {
        "tracer_provider": trace.get_tracer_provider(),
        "meter_provider": metrics.get_meter_provider(),
        "sqlite3.connect": sqlite3.connect,
        "tracing._tracer_provider": tracing._tracer_provider,
    }


@contextmanager
def _isolated_setup_provider() -> Iterator[None]:
    """Stub what _setup_provider installs process-wide, so later tests keep theirs."""
    saved = tracing._tracer_provider
    with (
        mock.patch("opentelemetry.trace.set_tracer_provider"),
        mock.patch("opentelemetry.metrics.set_meter_provider"),
        mock.patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"),
        mock.patch("opentelemetry.instrumentation.celery.CeleryInstrumentor"),
        mock.patch("opentelemetry.instrumentation.requests.RequestsInstrumentor"),
        mock.patch("opentelemetry.instrumentation.dbapi.trace_integration"),
        mock.patch("telemetry.tracing.atexit.register"),
    ):
        try:
            yield
        finally:
            tracing._tracer_provider = saved


class InitTracingTest(TestCase):
    """Tests for init_tracing function."""

    def setUp(self):
        from telemetry import tracing

        tracing._tracing_initialized = False
        tracing._tracer_provider = None

    def tearDown(self):
        from telemetry import tracing

        tracing._tracing_initialized = False
        tracing._tracer_provider = None

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


class ResourceAttributesTest(TestCase):
    """Tests for resource attributes on TracerProvider."""

    def setUp(self):
        from telemetry import tracing

        tracing._tracing_initialized = False
        tracing._tracer_provider = None

    def tearDown(self):
        from telemetry import tracing

        tracing._tracing_initialized = False
        tracing._tracer_provider = None

    @mock.patch("telemetry.tracing._setup_provider")
    def test_resource_includes_deployment_environment(self, mock_setup):
        """Resource attributes include deployment.environment from NODE_ENV."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "NODE_ENV": "prod",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            init_tracing()
        mock_setup.assert_called_once()
        resource = mock_setup.call_args[0][0]
        self.assertEqual(resource.attributes.get("deployment.environment.name"), "prod")

    @mock.patch("telemetry.tracing._setup_provider")
    def test_resource_includes_service_version(self, mock_setup):
        """Resource attributes include service.version from pyproject.toml."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            init_tracing()
        mock_setup.assert_called_once()
        resource = mock_setup.call_args[0][0]
        version = resource.attributes.get("service.version")
        self.assertIsNotNone(version)
        self.assertRegex(version, r"^\d+\.\d+\.\d+")

    @mock.patch("telemetry.tracing._setup_provider")
    def test_resource_includes_instance_id(self, mock_setup):
        """Resource attributes include service.instance.id (hostname)."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            init_tracing()
        mock_setup.assert_called_once()
        resource = mock_setup.call_args[0][0]
        instance_id = resource.attributes.get("service.instance.id")
        self.assertIsNotNone(instance_id)
        self.assertTrue(len(instance_id) > 0)

    @mock.patch("telemetry.tracing._setup_provider")
    def test_default_environment_is_dev(self, mock_setup):
        """deployment.environment defaults to 'dev' when NODE_ENV unset."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("NODE_ENV", None)
            init_tracing()
        mock_setup.assert_called_once()
        resource = mock_setup.call_args[0][0]
        self.assertEqual(resource.attributes.get("deployment.environment.name"), "dev")

    @mock.patch("telemetry.tracing._setup_provider")
    def test_service_namespace_default_draftforge(self, mock_setup):
        """service.namespace defaults to 'draftforge' when env var unset."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("OTEL_SERVICE_NAMESPACE", None)
            init_tracing()
        mock_setup.assert_called_once()
        resource = mock_setup.call_args[0][0]
        self.assertEqual(resource.attributes.get("service.namespace"), "draftforge")

    @mock.patch("telemetry.tracing._setup_provider")
    def test_no_deprecated_deployment_environment_key(self, mock_setup):
        """`deployment.environment` (deprecated, no `.name`) is NOT set.

        Emitting both the deprecated and current keys confuses downstream
        consumers (Grafana Cloud's OTLP translator occasionally trips on the
        duplicate).
        """
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "NODE_ENV": "prod",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("OTEL_RESOURCE_ATTRIBUTES", None)
            init_tracing()
        resource = mock_setup.call_args[0][0]
        self.assertIsNone(resource.attributes.get("deployment.environment"))
        self.assertEqual(resource.attributes.get("deployment.environment.name"), "prod")


class DjangoInstrumentorHooksTest(TestCase):
    """Tests for DjangoInstrumentor request/response hooks."""

    def setUp(self):
        from telemetry import tracing

        tracing._tracing_initialized = False
        tracing._tracer_provider = None

    def tearDown(self):
        from telemetry import tracing

        tracing._tracing_initialized = False
        tracing._tracer_provider = None

    def test_setup_provider_instruments_django_with_hooks(self):
        """_setup_provider calls DjangoInstrumentor with hooks and exclusions."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            from telemetry.tracing import _build_resource

            resource = _build_resource()

        with (
            _isolated_setup_provider(),
            mock.patch(
                "opentelemetry.instrumentation.django.DjangoInstrumentor"
            ) as MockInstr,
        ):
            from telemetry.tracing import _setup_provider

            mock_provider = mock.MagicMock()
            _setup_provider(resource, mock_provider, "http://localhost:4317", {}, 0.1)

            instrument_call = MockInstr.return_value.instrument
            instrument_call.assert_called_once()
            call_kwargs = instrument_call.call_args[1]
            self.assertIn("request_hook", call_kwargs)
            self.assertIn("response_hook", call_kwargs)
            self.assertEqual(call_kwargs["excluded_urls"], "health,ready,metrics")


class DiagnosticMetricExporterTest(TestCase):
    """The metric exporter wrapper must work across OTLP SDK `_export` signatures."""

    def _build_exporter(self) -> "OTLPMetricExporter":
        from telemetry.tracing import _build_resource, _setup_provider

        env = {"OTEL_ENABLED": "true", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://x"}
        with (
            _isolated_setup_provider(),
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch(
                "opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"
            ) as MockReader,
            mock.patch("opentelemetry.sdk.metrics.MeterProvider"),
            mock.patch("opentelemetry.metrics.set_meter_provider"),
            mock.patch("opentelemetry.instrumentation.django.DjangoInstrumentor"),
        ):
            _setup_provider(_build_resource(), mock.MagicMock(), "http://x", {}, 0.1)
        return MockReader.call_args[0][0]

    def test_sdk_1_20_signature_without_timeout(self) -> None:
        exporter = self._build_exporter()
        resp = mock.MagicMock(status_code=200)

        def old_export(self, serialized_data):
            return resp

        with mock.patch.object(OTLPMetricExporter, "_export", old_export):
            self.assertIs(exporter._export(b"payload"), resp)

    def test_sdk_1_41_signature_forwards_timeout(self) -> None:
        exporter = self._build_exporter()
        resp = mock.MagicMock(status_code=200)
        seen: dict[str, float | None] = {}

        def new_export(self, serialized_data, timeout_sec=None):
            seen["timeout_sec"] = timeout_sec
            return resp

        with mock.patch.object(OTLPMetricExporter, "_export", new_export):
            self.assertIs(exporter._export(b"payload", 5.0), resp)
        self.assertEqual(seen["timeout_sec"], 5.0)

    def test_logs_rejected_batch_body(self) -> None:
        exporter = self._build_exporter()
        resp = mock.MagicMock(
            status_code=400, reason="Bad Request", text="bad temporality"
        )

        with (
            mock.patch.object(OTLPMetricExporter, "_export", lambda self, data: resp),
            mock.patch("telemetry.logging.get_logger") as mock_get_logger,
        ):
            exporter._export(b"payload")

        mock_get_logger.return_value.error.assert_called_once()
        kwargs = mock_get_logger.return_value.error.call_args[1]
        self.assertEqual(kwargs["status_code"], 400)
        self.assertEqual(kwargs["body"], "bad temporality")


class SetupProviderTestsLeaveGlobalsAloneTest(TestCase):
    """_setup_provider installs process-wide providers; its tests must not keep them."""

    def test_process_globals_survive_the_setup_provider_tests(self) -> None:
        before = _otel_globals()
        for case in (
            DjangoInstrumentorHooksTest(
                "test_setup_provider_instruments_django_with_hooks"
            ),
            DiagnosticMetricExporterTest("test_sdk_1_20_signature_without_timeout"),
        ):
            result = unittest.TestResult()
            case.run(result)
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        for name, value in _otel_globals().items():
            self.assertIs(value, before[name], name)
