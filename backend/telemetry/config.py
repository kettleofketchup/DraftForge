"""Central telemetry configuration and initialization."""

import logging
import os

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


def init_telemetry() -> None:
    """
    Initialize telemetry subsystems.

    Call once at Django startup (in settings.py or wsgi/asgi.py).
    Safe to call multiple times - subsequent calls are no-ops.
    """
    # Import here to avoid circular imports
    from telemetry.logging import configure_logging, get_logger
    from telemetry.tracing import init_tracing

    # Check master switch
    if not env_bool("TELEMETRY_ENABLED", True):
        _bootstrap_log.info("Telemetry disabled via TELEMETRY_ENABLED=false")
        return

    # Configure structlog
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_format = os.environ.get("LOG_FORMAT", "pretty" if is_dev() else "json")
    configure_logging(level=log_level, format=log_format)

    # Get a logger now that structlog is configured
    log = get_logger(__name__)

    # Initialize OTel tracing (no-op if not configured)
    init_tracing()

    # Log startup summary
    log.info(
        "telemetry_initialized",
        otel_enabled=env_bool("OTEL_ENABLED", False),
        log_format=log_format,
        log_level=log_level,
        service_name=get_service_name(),
    )
