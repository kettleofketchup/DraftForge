"""OpenTelemetry tracing and log export configuration."""

import atexit
import logging
import os
from pathlib import Path

# Use stdlib logging for bootstrap messages
_log = logging.getLogger("telemetry.tracing")

# Track initialization state
_tracing_initialized = False
_log_export_initialized = False
_log_provider = None


def _get_otel_config() -> tuple[str, dict[str, str]] | None:
    """Return (endpoint, headers) if OTel is enabled and configured, else None."""
    from telemetry.config import env_bool, parse_otlp_headers

    if not env_bool("OTEL_ENABLED", False):
        return None
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None
    return endpoint, parse_otlp_headers()


def _get_service_version() -> str:
    """Read service version from pyproject.toml."""
    try:
        import tomllib

        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version", "unknown")
    except Exception:
        return "unknown"


def _build_resource() -> "Resource":
    """Build OTel Resource with deployment attributes."""
    import socket

    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    service_name = os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")
    environment = os.environ.get("NODE_ENV", "dev")
    version = _get_service_version()
    instance_id = socket.gethostname()

    return Resource.create(
        {
            SERVICE_NAME: service_name,
            "deployment.environment": environment,
            "service.version": version,
            "service.instance.id": instance_id,
        }
    )


def _setup_provider(resource, provider, endpoint, header_dict, sample_rate) -> None:
    """Configure TracerProvider with exporters and instrumentors."""
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = resource.attributes.get("service.name", "dtx-backend")

    exporter = OTLPSpanExporter(
        endpoint=endpoint + "/v1/traces", headers=header_dict or None
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Instrument Django with hooks for request/user correlation
    try:
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        def _request_hook(span, request):
            """Inject request ID into OTel span for correlation with structlog."""
            request_id = request.META.get("HTTP_X_REQUEST_ID", "")
            if request_id:
                span.set_attribute("http.request.id", request_id)

        def _response_hook(span, request, response):
            """Inject user ID into OTel span (AuthenticationMiddleware has run by now)."""
            if hasattr(request, "user") and request.user.is_authenticated:
                span.set_attribute("enduser.id", str(request.user.pk))

        DjangoInstrumentor().instrument(
            request_hook=_request_hook,
            response_hook=_response_hook,
            excluded_urls="health,ready,metrics",
        )
    except Exception as e:
        _log.warning(f"Failed to instrument Django: {e}")

    # Instrument requests (for outbound HTTP)
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
    except Exception as e:
        _log.warning(f"Failed to instrument requests: {e}")

    # Instrument system metrics
    try:
        from opentelemetry.instrumentation.system_metrics import (
            SystemMetricsInstrumentor,
        )

        SystemMetricsInstrumentor().instrument()
    except Exception as e:
        _log.warning(f"Failed to instrument system metrics: {e}")

    # Instrument database (SQLite via dbapi)
    try:
        import sqlite3

        from opentelemetry.instrumentation.dbapi import trace_integration

        trace_integration(sqlite3, "connect", "sqlite", capture_parameters=False)
    except Exception as e:
        _log.warning(f"Failed to instrument database: {e}")

    _log.info(
        f"OpenTelemetry tracing initialized: endpoint={endpoint}, "
        f"service={service_name}, sample_rate={sample_rate}"
    )


def init_tracing() -> None:
    """
    Initialize OpenTelemetry tracing.

    Configures OTLP exporter if OTEL_ENABLED=true and endpoint is configured.
    Safe to call multiple times - subsequent calls are no-ops.

    Environment Variables:
        OTEL_ENABLED: Enable tracing (default: false)
        OTEL_SERVICE_NAME: Service name (default: dtx-backend)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL
        OTEL_EXPORTER_OTLP_HEADERS: Optional auth headers
        OTEL_TRACES_SAMPLER_ARG: Sample rate (default: 0.1 = 10%)
    """
    global _tracing_initialized

    if _tracing_initialized:
        return

    config = _get_otel_config()
    if config is None:
        _log.info("OpenTelemetry tracing disabled (not enabled or no endpoint)")
        _tracing_initialized = True
        return

    endpoint, header_dict = config

    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        resource = _build_resource()
        sample_rate = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "0.1"))
        sampler = ParentBased(root=TraceIdRatioBased(sample_rate))

        provider = TracerProvider(resource=resource, sampler=sampler)
        _setup_provider(resource, provider, endpoint, header_dict, sample_rate)

    except ImportError as e:
        _log.warning(f"OpenTelemetry packages not available: {e}")
    except Exception as e:
        _log.error(f"Failed to initialize OpenTelemetry tracing: {e}")

    _tracing_initialized = True


def init_log_export():
    """
    Initialize OpenTelemetry log export to ship logs via OTLP.

    Returns the LoggerProvider if configured, or None if disabled.
    Reuses the same endpoint/auth configuration as tracing.
    """
    global _log_export_initialized, _log_provider

    if _log_export_initialized:
        return _log_provider

    config = _get_otel_config()
    if config is None:
        _log.info("OTel log export disabled (not enabled or no endpoint)")
        _log_export_initialized = True
        return None

    endpoint, header_dict = config

    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        _log_provider = LoggerProvider(resource=_build_resource())
        set_logger_provider(_log_provider)

        exporter = OTLPLogExporter(
            endpoint=endpoint + "/v1/logs", headers=header_dict or None
        )
        _log_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

        atexit.register(_shutdown_log_provider)

        _log.info(f"OTel log export initialized: endpoint={endpoint}")

    except ImportError as e:
        _log.warning(f"OTel log export packages not available: {e}")
    except Exception as e:
        _log.error(f"Failed to initialize OTel log export: {e}")

    _log_export_initialized = True
    return _log_provider


def _shutdown_log_provider():
    """Flush remaining logs on process exit."""
    if _log_provider is not None:
        _log_provider.shutdown()
