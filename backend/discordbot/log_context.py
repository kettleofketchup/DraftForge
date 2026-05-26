"""Async context manager that ties Discord interactions to structured logs + OTel spans.

Every callback in discordbot/components.py wraps its body with discord_log_context.
The CM:
  - opens an OTel span (lazy tracer lookup — never cache the tracer module-level
    or test fixtures cannot install a TracerProvider)
  - binds interaction identity into structlog contextvars so every downstream log
    line in handlers/services/dispatch/Celery inherits the context
  - emits interaction_started / interaction_finished / interaction_failed bookend
    logs with identity fields passed EXPLICITLY as kwargs so they survive
    structlog.testing.capture_logs() (which strips merge_contextvars)
"""

from __future__ import annotations

from typing import Any


class InteractionContext:
    """Yielded by discord_log_context; lets handlers annotate the closing log."""

    def __init__(self) -> None:
        self.outcome: str | None = None
        self.extra: dict[str, Any] = {}

    def set_outcome(self, outcome: str) -> None:
        self.outcome = outcome

    def add(self, **kwargs: Any) -> None:
        self.extra.update(kwargs)
