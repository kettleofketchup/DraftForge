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


# init_telemetry() will be added in Task 6b after logging.py and tracing.py exist
