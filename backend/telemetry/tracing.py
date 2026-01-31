"""OpenTelemetry tracing configuration."""

import logging
import os

# Use stdlib logging for bootstrap messages
_log = logging.getLogger("telemetry.tracing")

# Track initialization state
_initialized = False


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
    global _initialized

    if _initialized:
        return

    # Import from config (CRITICAL FIX #6)
    from telemetry.config import env_bool

    # Check if OTel is enabled
    if not env_bool("OTEL_ENABLED", False):
        _log.info("OpenTelemetry disabled (OTEL_ENABLED not set or false)")
        _initialized = True
        return

    # Check for endpoint
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _log.info("OpenTelemetry disabled (no OTLP endpoint configured)")
        _initialized = True
        return

    try:
        # Import OTel modules
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        # Get configuration
        service_name = os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")
        sample_rate = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "0.1"))
        headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")

        # Parse headers (format: "key1=value1,key2=value2")
        header_dict: dict[str, str] = {}
        if headers:
            for pair in headers.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    header_dict[key.strip()] = value.strip()

        # Create resource
        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
            }
        )

        # Create sampler
        sampler = TraceIdRatioBased(sample_rate)

        # Create tracer provider
        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Create exporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=header_dict or None,
        )

        # Add processor
        provider.add_span_processor(BatchSpanProcessor(exporter))

        # Set global tracer provider
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
            f"OpenTelemetry initialized: endpoint={endpoint}, "
            f"service={service_name}, sample_rate={sample_rate}"
        )

    except ImportError as e:
        _log.warning(f"OpenTelemetry packages not available: {e}")
    except Exception as e:
        _log.error(f"Failed to initialize OpenTelemetry: {e}")

    _initialized = True
