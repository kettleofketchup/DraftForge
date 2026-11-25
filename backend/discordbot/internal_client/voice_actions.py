"""HTTP wrappers for the bot's voice presence feed.

Same contract as ``bot_actions.py``: synchronous, plain-dict results
validated through ``discordbot/schemas.py``, and a typed fallback instead
of an exception when the backend is unreachable.
"""

from __future__ import annotations

from typing import Any

import requests

from app.internal_client import transport
from discordbot.schemas import VoicePresenceResponse, WatchedChannelsResponse


def _watched_fallback() -> dict[str, Any]:
    return {"available": False, "channels": [], "ttl_seconds": 60}


def _presence_fallback() -> dict[str, Any]:
    return VoicePresenceResponse(
        success=False, detail="internal_api_unreachable"
    ).model_dump()


def _json(resp: requests.Response | None) -> Any | None:
    if resp is None or not resp.ok:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def get_watched_channels() -> dict[str, Any]:
    """Return ``{available, channels, ttl_seconds}`` for the bot's watch map."""
    payload = _json(transport.get("/discord/voice/watched-channels/"))
    if payload is None:
        return _watched_fallback()
    return WatchedChannelsResponse.model_validate(payload).model_dump()


def report_voice_state(
    *,
    guild_id: str,
    discord_user_id: str,
    before_channel_id: str | None,
    after_channel_id: str | None,
) -> dict[str, Any]:
    """Report one member's voice channel change."""
    payload = _json(
        transport.post(
            "/discord/voice/state/",
            {
                "guild_id": str(guild_id),
                "discord_user_id": str(discord_user_id),
                "before_channel_id": before_channel_id,
                "after_channel_id": after_channel_id,
            },
        )
    )
    if payload is None:
        return _presence_fallback()
    return VoicePresenceResponse.model_validate(payload).model_dump()


def post_voice_snapshot(
    *,
    guild_id: str,
    channels: list[dict[str, Any]],
    missing_channel_ids: list[str],
) -> dict[str, Any]:
    """Post the full member list of each visible watched channel in a guild."""
    payload = _json(
        transport.post(
            "/discord/voice/snapshot/",
            {
                "guild_id": str(guild_id),
                "channels": channels,
                "missing_channel_ids": missing_channel_ids,
            },
        )
    )
    if payload is None:
        return _presence_fallback()
    return VoicePresenceResponse.model_validate(payload).model_dump()
