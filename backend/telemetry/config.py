"""Central telemetry configuration and initialization."""

import logging
import os
from urllib.parse import unquote

# Use stdlib logging until structlog is configured
_bootstrap_log = logging.getLogger("telemetry.config")


def env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean environment variable."""
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    return default


def is_dev() -> bool:
    """Check if running in development environment."""
    node_env = os.environ.get("NODE_ENV", "dev")
    return node_env in ("dev", "development")


def get_service_name() -> str:
    """Get the service name for telemetry."""
    return os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")


def parse_otlp_headers() -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS into a dict, URL-decoding values."""
    raw = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    headers: dict[str, str] = {}
    if raw:
        for pair in raw.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                headers[key.strip()] = unquote(value.strip())
    return headers


def init_telemetry() -> None:
    """
    Initialize telemetry subsystems.

    Call once at Django startup (in settings.py or wsgi/asgi.py).
    Safe to call multiple times - subsequent calls are no-ops.
    """
    # Import here to avoid circular imports
    from telemetry.logging import configure_logging
    from telemetry.tracing import init_log_export, init_tracing

    # Check master switch
    if not env_bool("TELEMETRY_ENABLED", True):
        _bootstrap_log.info("Telemetry disabled via TELEMETRY_ENABLED=false")
        return

    # Initialize OTel tracing first (no-op if not configured)
    init_tracing()

    # Initialize OTel log export (returns provider or None)
    otel_logger_provider = init_log_export()

    # Configure structlog (with optional OTel log handler)
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_format = os.environ.get("LOG_FORMAT", "pretty" if is_dev() else "json")
    configure_logging(
        level=log_level, format=log_format, otel_logger_provider=otel_logger_provider
    )
