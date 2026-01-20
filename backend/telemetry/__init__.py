"""
DTX Backend Telemetry Module

Provides structured logging (structlog) and optional distributed tracing (OpenTelemetry)
with consistent context propagation across HTTP requests, WebSockets, and Celery tasks.

Usage:
    from telemetry.config import init_telemetry
    init_telemetry()  # Call once at Django startup
"""

# init_telemetry will be imported after it's implemented in Task 6b
# from telemetry.config import init_telemetry
# __all__ = ["init_telemetry"]
