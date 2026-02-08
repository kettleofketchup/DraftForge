"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Literal

import structlog
from structlog.typing import Processor

# Track if logging has been configured
_configured = False


class _OTelInternalFilter(logging.Filter):
    """Prevent OTel's own log messages from being re-ingested by the OTel handler."""

    def filter(self, record):
        return not record.name.startswith("opentelemetry")


def _add_otel_trace_context(logger, method_name, event_dict):
    """Inject OpenTelemetry trace/span IDs into log events for correlation."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass
    return event_dict


def configure_logging(
    level: str = "INFO",
    format: Literal["json", "pretty"] = "json",
    otel_logger_provider=None,
) -> None:
    """
    Configure structlog for the application.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        format: Output format - 'json' for production, 'pretty' for development
        otel_logger_provider: Optional OTel LoggerProvider to ship logs via OTLP
    """
    global _configured

    # Shared processors for all output formats
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _add_otel_trace_context,
    ]

    if format == "json":
        # JSON output for production
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Pretty console output for development
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )

    # Configure structlog
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Add OTel log export handler (ships logs to Loki via OTLP)
    if otel_logger_provider is not None:
        from opentelemetry.sdk._logs import LoggingHandler

        otel_handler = LoggingHandler(
            level=logging.INFO,  # Don't export DEBUG to Loki
            logger_provider=otel_logger_provider,
        )
        # Prevent OTel's own logs from being re-ingested (infinite recursion)
        otel_handler.addFilter(_OTelInternalFilter())
        root_logger.addHandler(otel_handler)

    # Quiet noisy third-party loggers
    for logger_name in ["urllib3", "requests", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structlog logger for the given module name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        A bound structlog logger
    """
    return structlog.get_logger(name)
