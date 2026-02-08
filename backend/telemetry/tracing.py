"""OpenTelemetry tracing and log export configuration."""

import atexit
import logging
import os

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
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        service_name = os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")
        sample_rate = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "0.1"))

        resource = Resource.create({SERVICE_NAME: service_name})
        sampler = TraceIdRatioBased(sample_rate)

        provider = TracerProvider(resource=resource, sampler=sampler)
        exporter = OTLPSpanExporter(
            endpoint=endpoint + "/v1/traces", headers=header_dict or None
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Instrument Django
        try:
            from opentelemetry.instrumentation.django import DjangoInstrumentor

            DjangoInstrumentor().instrument()
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

        _log.info(
            f"OpenTelemetry tracing initialized: endpoint={endpoint}, "
            f"service={service_name}, sample_rate={sample_rate}"
        )

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
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource

        service_name = os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")
        resource = Resource.create({SERVICE_NAME: service_name})

        _log_provider = LoggerProvider(resource=resource)
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
