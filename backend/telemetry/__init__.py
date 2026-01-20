"""
DTX Backend Telemetry Module

Provides structured logging (structlog) and optional distributed tracing (OpenTelemetry)
with consistent context propagation across HTTP requests, WebSockets, and Celery tasks.

Usage:
    from telemetry.config import init_telemetry
    init_telemetry()  # Call once at Django startup
"""

from telemetry.config import init_telemetry

__all__ = ["init_telemetry"]
