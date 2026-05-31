"""Server-side handlers for the Discord bot's gateway-side flows.

These functions encapsulate ORM work for surfaces that used to run in-process
inside ``discordbot/bot.py``: the ``/event`` slash-command admin check, the
``/event`` create command, and the legacy ScheduledEvent + RSVP reaction
flow. They run in the backend (Daphne) container, which is the sole DB
writer; the bot calls them over HTTP via
``discordbot/internal_client/bot_actions.py``.

Each function is pure and synchronous — the HTTP view wraps it and the
client wrapper runs it via ``sync_to_async`` in the bot process.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from app.models import CustomUser
from discordbot.models import RSVP, EventTemplate, ScheduledEvent


def check_site_admin(*, discord_user_id: str) -> dict[str, Any]:
    """Return admin/link status for a Discord ID.

    ``is_linked=False`` distinguishes "no CustomUser row" from "user found
    but not staff". The decorator translates these into the original
    CheckFailure messages.
    """
    try:
        user = CustomUser.objects.get(discordId=str(discord_user_id))
    except CustomUser.DoesNotExist:
        return {"is_admin": False, "is_linked": False, "error": None}
    return {"is_admin": bool(user.is_staff), "is_linked": True, "error": None}


def set_legacy_rsvp(
    *,
    discord_message_id: str,
    discord_user_id: str,
    status: str,
    discord_username: str,
) -> dict[str, Any]:
    """Create or update an RSVP for a legacy ScheduledEvent message.

    Returns ``{success: False, error: "not_event_message"}`` when the message
    is not a tracked ScheduledEvent — callers treat that as a no-op (the
    reaction was on something else).
    """
    try:
        event = ScheduledEvent.objects.get(
            discord_message_id=str(discord_message_id)
        )
    except ScheduledEvent.DoesNotExist:
        return {
            "success": False,
            "error": "not_event_message",
            "event_name": None,
        }

    RSVP.objects.update_or_create(
        scheduled_event=event,
        discord_user_id=str(discord_user_id),
        defaults={
            "discord_username": discord_username,
            "status": status,
        },
    )
    return {
        "success": True,
        "error": None,
        "event_name": event.template.name,
    }


def remove_legacy_rsvp(
    *,
    discord_message_id: str,
    discord_user_id: str,
) -> dict[str, Any]:
    """Remove a legacy RSVP. No-op when the message isn't a ScheduledEvent."""
    try:
        event = ScheduledEvent.objects.get(
            discord_message_id=str(discord_message_id)
        )
    except ScheduledEvent.DoesNotExist:
        return {
            "success": False,
            "error": "not_event_message",
            "event_name": None,
        }

    RSVP.objects.filter(
        scheduled_event=event,
        discord_user_id=str(discord_user_id),
    ).delete()
    return {
        "success": True,
        "error": None,
        "event_name": event.template.name,
    }


def create_legacy_event(
    *,
    name: str,
    description: str,
    channel_id: str,
) -> dict[str, Any]:
    """Create a one-time EventTemplate + ScheduledEvent posted immediately.

    Mirrors the original ``/event`` slash-command body verbatim so the
    bot-side behaviour is unchanged.
    """
    template = EventTemplate.objects.create(
        name=name,
        template_type="announcement",
        title=name,
        description=description,
        color="#5865F2",
        channel_id=str(channel_id),
        include_rsvp=True,
    )
    event = ScheduledEvent.objects.create(
        template=template,
        next_post_at=timezone.now(),
        is_recurring=False,
    )
    return {"success": True, "error": None, "event_id": event.pk}
