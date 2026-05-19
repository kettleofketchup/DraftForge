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
_tracer_provider = None


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
            "deployment.environment.name": environment,
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

    global _tracer_provider
    _tracer_provider = provider
    atexit.register(_shutdown_tracer_provider)

    # Configure metrics export.
    #
    # Grafana Cloud Mimir's OTLP ingest uses the OpenTelemetry Collector's
    # Prometheus remote-write translator. That translator rejects DELTA
    # temporality for every Sum and Histogram type — see
    # `isValidAggregationTemporality` in
    # open-telemetry/opentelemetry-collector-contrib :
    # pkg/translator/prometheusremotewrite/helper.go . Accepted combinations:
    #
    #   Gauge / Summary  : DELTA or CUMULATIVE (temporality ignored)
    #   Sum (Counter, UpDownCounter, Observable{Up,Down}Counter)  : CUMULATIVE
    #   Histogram, ExponentialHistogram                            : CUMULATIVE
    #
    # The SDK default is CUMULATIVE for every instrument type, which matches
    # Mimir exactly. Older revisions of this file shipped a custom
    # `preferred_temporality` map that forced DELTA on Counter / Histogram /
    # ObservableCounter — the cause of the recurring
    # "invalid temporality and type combination" 400s on
    # `http.client.*`, `otel.sdk.*`, `flower.task.runtime.seconds`, etc.
    # Don't reintroduce that map. If a specific metric needs DELTA in the
    # future, override it with a per-instrument View, not globally.
    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.metrics.view import DropAggregation, View

        # Wrap the exporter so that when Grafana Cloud rejects a batch with a
        # 4xx the response body is captured to our logs. The stock SDK only
        # logs `code: 400, reason: Bad Request` which is useless — Grafana's
        # body carries the actual reason (e.g. "invalid temporality and type
        # combination for metric X"). Without this, diagnosing future
        # regressions required SSH + monkey-patching requests at runtime.
        class _DiagnosticMetricExporter(OTLPMetricExporter):
            def _export(self, serialized_data, timeout_sec=None):
                resp = super()._export(serialized_data, timeout_sec)
                if 400 <= resp.status_code < 500:
                    body = (resp.text or "")[:1000].replace("\x00", "?")
                    from telemetry.logging import get_logger

                    get_logger(__name__).error(
                        "otlp_metric_export_rejected",
                        system="telemetry",
                        subsystem="otlp",
                        status_code=resp.status_code,
                        reason=resp.reason,
                        body=body,
                    )
                return resp

        metric_exporter = _DiagnosticMetricExporter(
            endpoint=endpoint + "/v1/metrics",
            headers=header_dict or None,
        )
        metric_reader = PeriodicExportingMetricReader(metric_exporter)

        # Drop metrics we don't want shipped:
        #
        # * http.client.* — requests instrumentation duplicates data we
        #   already get from server-side http.server.duration spans.
        #
        # * otel.sdk.* — the SDK's own self-monitoring metrics
        #   (collection.duration, exported.count, etc.). Exporter internals,
        #   not useful telemetry.
        #
        # * flower.* — Flower's task-runtime histogram (and friends) ship
        #   with DELTA temporality. Mimir's OTLP→PromRW translator only
        #   accepts CUMULATIVE for Histogram, so every batch containing a
        #   `flower.task.runtime.seconds` data point gets rejected with
        #   `otlp parse error: invalid temporality and type combination`.
        #   Flower's internal counters aren't useful for our Grafana
        #   dashboards anyway — drop them.
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
            views=[
                View(
                    instrument_name="http.client.duration",
                    aggregation=DropAggregation(),
                ),
                View(
                    instrument_name="http.client.request.size",
                    aggregation=DropAggregation(),
                ),
                View(
                    instrument_name="http.client.response.size",
                    aggregation=DropAggregation(),
                ),
                View(
                    instrument_name="otel.sdk.*",
                    aggregation=DropAggregation(),
                ),
                View(
                    instrument_name="flower.*",
                    aggregation=DropAggregation(),
                ),
            ],
        )
        metrics.set_meter_provider(meter_provider)
    except Exception as e:
        _log.warning(f"Failed to configure metrics export: {e}")

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

    # Instrument Celery task execution (creates root spans for every task)
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except Exception as e:
        _log.warning(f"Failed to instrument Celery: {e}")

    # Instrument requests (for outbound HTTP)
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
    except Exception as e:
        _log.warning(f"Failed to instrument requests: {e}")

    # System metrics (cpu, disk, network) intentionally NOT instrumented:
    # Grafana Cloud Mimir rejects the temporality/type combos they produce,
    # and host-level metrics from inside a container aren't useful anyway.

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
        _log.debug("OpenTelemetry tracing disabled (not enabled or no endpoint)")
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
        _log.debug("OTel log export disabled (not enabled or no endpoint)")
        _log_export_initialized = True
        return None

    endpoint, header_dict = config

    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogExportResult

        # SDK 1.20.0 only accepts 200/202; Grafana Cloud returns 204.
        # Accept all 2xx until we upgrade to a version that handles this.
        class _PatchedLogExporter(OTLPLogExporter):
            def export(self, batch):
                if self._shutdown:
                    return LogExportResult.FAILURE
                from opentelemetry.exporter.otlp.proto.common._log_encoder import encode_logs

                serialized_data = encode_logs(batch).SerializeToString()
                resp = self._export(serialized_data)
                if 200 <= resp.status_code < 300:
                    return LogExportResult.SUCCESS
                _log.warning("OTLP log export failed: %s %s", resp.status_code, resp.reason)
                return LogExportResult.FAILURE

        _log_provider = LoggerProvider(resource=_build_resource())
        set_logger_provider(_log_provider)

        exporter = _PatchedLogExporter(
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


def _shutdown_tracer_provider():
    """Flush remaining spans on process exit."""
    if _tracer_provider is not None:
        _tracer_provider.shutdown()


def _shutdown_log_provider():
    """Flush remaining logs on process exit."""
    if _log_provider is not None:
        _log_provider.shutdown()
