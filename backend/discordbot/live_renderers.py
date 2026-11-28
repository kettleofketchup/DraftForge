"""Backend-side renderers for named, opt-in Discord Components V2 messages."""

from collections.abc import Callable
from typing import Any

from events.capacity import with_signup_counts
from events.discord.embeds import build_subscriber_dm_v2
from events.models import Event


def _event_signup_reminder(subject_id: int) -> dict[str, Any] | None:
    event = (
        with_signup_counts(Event.objects.select_related("organization").nocache())
        .filter(pk=subject_id)
        .first()
    )
    if event is None:
        return None
    return build_subscriber_dm_v2(event, signup_count=event.signup_count)


RENDERERS: dict[str, Callable[[int], dict[str, Any] | None]] = {
    "event_signup_reminder": _event_signup_reminder,
}


def render_live_message(renderer: str, subject_id: int) -> dict[str, Any] | None:
    """Build current components, or return None when the subject was deleted."""
    try:
        build = RENDERERS[renderer]
    except KeyError:
        raise ValueError(f"Unknown live message renderer: {renderer}") from None
    return build(subject_id)
