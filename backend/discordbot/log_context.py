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

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from structlog.contextvars import bind_contextvars, clear_contextvars

# Single source of truth for signup-flow prefixes (see custom_ids.py).
from discordbot.custom_ids import SIGNUP_TAG_PREFIXES as _SIGNUP_TAG_PREFIXES
from telemetry.logging import get_logger

if TYPE_CHECKING:
    import discord

log = get_logger(__name__)


class InteractionContext:
    """Yielded by discord_log_context; lets handlers annotate the closing log."""

    def __init__(self) -> None:
        self.outcome: str | None = None
        self.extra: dict[str, Any] = {}

    def set_outcome(self, outcome: str) -> None:
        self.outcome = outcome

    def add(self, **kwargs: Any) -> None:
        self.extra.update(kwargs)


def _prefix(custom_id: str | None) -> str | None:
    if not custom_id:
        return None
    head = custom_id.split(":", 1)[0]
    # pos_select_<slot> normalizes to the codec prefix "pos_select" (the slot
    # lives in the prefix segment, unlike every other custom_id).
    if head.startswith("pos_select_"):
        return "pos_select"
    return head


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


def _interaction_type_name(interaction: discord.Interaction) -> str:
    """Map discord.InteractionType to a stable string for our logs."""
    try:
        return interaction.type.name
    except AttributeError:
        return "unknown"


def _identity_fields(
    interaction: discord.Interaction,
    *,
    custom_id: str | None,
    event_id: int | None,
    tags: list[str],
) -> dict[str, Any]:
    """The set of identity fields bound to contextvars AND passed to bookend logs."""
    return {
        "system": "discord",
        "subsystem": "interaction",
        "tags": tags,
        "tags_csv": tags_csv(tags),
        "interaction_id": str(interaction.id),
        "discord_user_id": str(interaction.user.id),
        "discord_username": interaction.user.name,
        "channel_id": str(interaction.channel_id) if interaction.channel_id else None,
        "guild_id": str(interaction.guild_id)
        if getattr(interaction, "guild_id", None)
        else None,
        "interaction_type": _interaction_type_name(interaction),
        "custom_id": custom_id,
        "event_id": event_id,
    }


@asynccontextmanager
async def discord_log_context(
    interaction: discord.Interaction,
    *,
    custom_id: str | None = None,
    event_id: int | None = None,
    tags: list[str] | None = None,
) -> AsyncIterator[InteractionContext]:
    """Bind interaction identity to logs + emit bookend events."""
    resolved_custom_id = custom_id or (
        interaction.data.get("custom_id")
        if getattr(interaction, "data", None)
        else None
    )
    resolved_event_id = (
        event_id if event_id is not None else parse_event_id(resolved_custom_id)
    )
    resolved_tags = tags if tags is not None else resolve_tags(resolved_custom_id)

    fields = _identity_fields(
        interaction,
        custom_id=resolved_custom_id,
        event_id=resolved_event_id,
        tags=resolved_tags,
    )

    tracer = trace.get_tracer(
        __name__
    )  # Lazy — test fixtures install processors AFTER import
    with tracer.start_as_current_span(span_name(resolved_custom_id)) as span:
        # Span attributes mirror the bound contextvars
        for key, val in fields.items():
            if val is None:
                continue
            if key == "discord_user_id":
                span.set_attribute("discord.user_id", val)
            elif key == "discord_username":
                span.set_attribute("discord.username", val)
            elif key == "tags":
                continue  # Lists aren't valid OTel attributes; tags_csv carries the same data
            else:
                span.set_attribute(key, val)

        bind_contextvars(**fields)
        log.info("interaction_started", **fields)

        ctx = InteractionContext()
        try:
            yield ctx
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            log.error(
                "interaction_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
                **fields,
                **ctx.extra,
            )
            clear_contextvars()
            raise
        else:
            log.info(
                "interaction_finished",
                outcome=ctx.outcome or "ok",
                **fields,
                **ctx.extra,
            )
            clear_contextvars()
