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


_SIGNUP_TAG_PREFIXES = {
    "event_signup", "event_notify", "event_tentative", "event_decline",
    "signup_friend_id", "signup_rank_status", "signup_deadlock_rank", "signup_deadlock_date",
    "pos_select_1", "pos_select_2", "pos_select_3", "pos_confirm",
    "rank_medal", "rank_star", "rank_status",
    "bcup_tier",
    "screenshot_upload", "screenshot_file", "screenshot_url",
}


def _prefix(custom_id: str | None) -> str | None:
    if not custom_id:
        return None
    return custom_id.split(":", 1)[0]


def resolve_tags(custom_id: str | None) -> list[str]:
    """Map a custom_id prefix to its cross-cutting tags. Unknown → []."""
    return ["events", "signup"] if _prefix(custom_id) in _SIGNUP_TAG_PREFIXES else []


def tags_csv(tags: list[str]) -> str:
    """Join tags with a comma for clean LogQL filtering (avoids array-flattening)."""
    return ",".join(tags)


def parse_event_id(custom_id: str | None) -> int | None:
    """Pull the event_id out of `prefix:event_id[:extra]`. Non-int → None."""
    if not custom_id or ":" not in custom_id:
        return None
    try:
        return int(custom_id.split(":")[1])
    except (ValueError, IndexError):
        return None


def span_name(custom_id: str | None) -> str:
    """Strip the `:event_id` suffix and prefix with `discord.interaction.`."""
    return f"discord.interaction.{_prefix(custom_id) or 'unknown'}"
