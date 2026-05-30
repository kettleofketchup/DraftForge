"""HTTP wrappers for the Discord bot's gateway-side ORM call surfaces.

Mirrors ``signup_actions.py`` but covers the surfaces that used to live
inline in ``discordbot/bot.py``: the ``/event`` admin check, reaction
signups/cancels (new-style event messages), and the legacy ScheduledEvent
RSVP + ``/event`` slash-command create flows.

The bot process has no DB mount in production, so any direct ORM access
from this code path fails with ``sqlite3.OperationalError: unable to open
database file``. Every call here POSTs to the backend's internal API
instead — the backend remains the sole DB writer.

Each wrapper is synchronous and returns a plain dict so the bot's existing
``await sync_to_async(...)`` patterns work unchanged. Responses are
validated through the matching pydantic response schema in
``discordbot/schemas.py`` and re-emitted as dicts so callers stay
behaviour-compatible. Network/HTTP errors return a typed "unavailable"
default dict (no exceptions surface to the bot).
"""

from __future__ import annotations

from typing import Any

from app.internal_client import _post
from discordbot.schemas import (
    LegacyEventCreateResponse,
    LegacyRsvpResponse,
    ReactionResponse,
    SiteAdminCheckResponse,
)


def check_site_admin(*, discord_user_id: str) -> dict[str, Any]:
    """Look up admin/link status for the /event slash-command decorator.

    Returns ``{is_admin, is_linked, error}``. On transport failure,
    ``error="internal_api_unreachable"`` so the decorator can surface a
    distinct CheckFailure rather than silently allowing the command.
    """
    resp = _post(
        "/discord/check-site-admin/",
        {"discord_user_id": str(discord_user_id)},
    )
    if resp is None or not resp.ok:
        return {
            "is_admin": False,
            "is_linked": False,
            "error": "internal_api_unreachable",
        }
    try:
        payload = resp.json()
    except ValueError:
        return {
            "is_admin": False,
            "is_linked": False,
            "error": "internal_api_unreachable",
        }
    return SiteAdminCheckResponse.model_validate(payload).model_dump()


def reaction_signup(
    *,
    discord_message_id: str,
    discord_user_id: str,
) -> dict[str, Any]:
    """Run the new-style event reaction-signup flow over HTTP.

    Returns ``{success, detail}``. ``detail == "not_event_message"`` tells
    the bot to fall through to the legacy RSVP path.
    """
    resp = _post(
        "/discord/reaction-signup/",
        {
            "discord_message_id": str(discord_message_id),
            "discord_user_id": str(discord_user_id),
        },
    )
    if resp is None or not resp.ok:
        return {"success": False, "detail": "internal_api_unreachable"}
    try:
        payload = resp.json()
    except ValueError:
        return {"success": False, "detail": "internal_api_unreachable"}
    return ReactionResponse.model_validate(payload).model_dump()


def reaction_cancel(
    *,
    discord_message_id: str,
    discord_user_id: str,
) -> dict[str, Any]:
    """Run the new-style event reaction-cancel flow over HTTP.

    Returns ``{success, detail}``. ``detail == "not_event_message"`` tells
    the bot to fall through to the legacy RSVP path.
    """
    resp = _post(
        "/discord/reaction-cancel/",
        {
            "discord_message_id": str(discord_message_id),
            "discord_user_id": str(discord_user_id),
        },
    )
    if resp is None or not resp.ok:
        return {"success": False, "detail": "internal_api_unreachable"}
    try:
        payload = resp.json()
    except ValueError:
        return {"success": False, "detail": "internal_api_unreachable"}
    return ReactionResponse.model_validate(payload).model_dump()


def set_legacy_rsvp(
    *,
    discord_message_id: str,
    discord_user_id: str,
    status: str,
    discord_username: str,
) -> dict[str, Any]:
    """Create/update a legacy ScheduledEvent RSVP for an emoji reaction."""
    resp = _post(
        "/discord/legacy-rsvp/set/",
        {
            "discord_message_id": str(discord_message_id),
            "discord_user_id": str(discord_user_id),
            "status": status,
            "discord_username": discord_username,
        },
    )
    if resp is None or not resp.ok:
        return {
            "success": False,
            "error": "internal_api_unreachable",
            "event_name": None,
        }
    try:
        payload = resp.json()
    except ValueError:
        return {
            "success": False,
            "error": "internal_api_unreachable",
            "event_name": None,
        }
    return LegacyRsvpResponse.model_validate(payload).model_dump()


def remove_legacy_rsvp(
    *,
    discord_message_id: str,
    discord_user_id: str,
) -> dict[str, Any]:
    """Remove a legacy ScheduledEvent RSVP when the reaction is removed."""
    resp = _post(
        "/discord/legacy-rsvp/remove/",
        {
            "discord_message_id": str(discord_message_id),
            "discord_user_id": str(discord_user_id),
        },
    )
    if resp is None or not resp.ok:
        return {
            "success": False,
            "error": "internal_api_unreachable",
            "event_name": None,
        }
    try:
        payload = resp.json()
    except ValueError:
        return {
            "success": False,
            "error": "internal_api_unreachable",
            "event_name": None,
        }
    return LegacyRsvpResponse.model_validate(payload).model_dump()


def create_legacy_event(
    *,
    name: str,
    description: str,
    channel_id: str,
) -> dict[str, Any]:
    """Create a one-shot EventTemplate + ScheduledEvent (admin /event)."""
    resp = _post(
        "/discord/legacy-event/create/",
        {
            "name": name,
            "description": description,
            "channel_id": str(channel_id),
        },
    )
    if resp is None or not resp.ok:
        return {
            "success": False,
            "error": "internal_api_unreachable",
            "event_id": None,
        }
    try:
        payload = resp.json()
    except ValueError:
        return {
            "success": False,
            "error": "internal_api_unreachable",
            "event_id": None,
        }
    return LegacyEventCreateResponse.model_validate(payload).model_dump()
