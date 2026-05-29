"""Pydantic REQUEST schemas for the Discord bot's internal-API surface.

This file owns:
  * Schemas validating data returned by internal API endpoints the bot reads
    (``SyncDiscordStateSchema``, ``MessageLogSchema``, ``DiscordEventStateSchema``).
  * Request-body validators for the bot's signup-flow endpoints
    (``discordbot/internal_signup_views.py``) — they validate Discord-button
    transport payloads so they belong here with the bot.

RESPONSE schemas for those signup endpoints (``SignupActionResponse``,
``RankFlowStateResponse``) live in ``events/schemas.py`` since they are the
contract of the ``events.discord.handlers`` business logic, not the bot's
transport layer.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SyncDiscordStateSchema(BaseModel):
    """Validates: get_sync_discord_state() (app/views/internal.py)"""

    active_events: list[dict]
    existing_logs: list[list]  # [[source, source_id], ...]
    events_with_signup: list[int]
    events_with_scheduled: list[int]
    events_with_recent_attempt: list[int]

    model_config = {"extra": "ignore"}


class MessageLogSchema(BaseModel):
    """Validates: search_message_logs() (app/views/internal.py)"""

    id: int
    channel_id: str = ""
    source: str = ""
    source_id: Optional[int] = None
    discord_message_id: Optional[str] = None
    status_code: Optional[int] = None
    success: bool = False
    response_data: Optional[dict] = None
    created_at: Optional[str] = None

    model_config = {"extra": "ignore"}


class DiscordEventStateSchema(BaseModel):
    """Validates: get_discord_event_state() (app/views/internal.py)"""

    has_discord_event: bool = False
    discord_event_pk: Optional[int] = None
    scheduled_event_id: Optional[str] = None
    signup_posted: bool = False
    signup_message_id: Optional[str] = None
    signup_channel_id: Optional[str] = None
    signup_thread_id: Optional[str] = None
    fired_actions: list[str] = []
    has_dms: bool = False

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Internal signup-API request schemas (validated server-side in
# discordbot/internal_signup_views.py).
# ---------------------------------------------------------------------------


class SignupButtonRequest(BaseModel):
    event_id: int
    discord_user_id: str
    discord_username: Optional[str] = None
    model_config = {"extra": "ignore"}


class SignupModalSubmitRequest(BaseModel):
    event_id: int
    discord_user_id: str
    game_type: int
    values: dict
    model_config = {"extra": "ignore"}


class RankStatusSelectRequest(BaseModel):
    event_id: int
    discord_user_id: str
    rank_status: str
    model_config = {"extra": "ignore"}


class RankMedalSelectRequest(BaseModel):
    event_id: int
    discord_user_id: str
    medal: str
    model_config = {"extra": "ignore"}


class PreviousRankSubmitRequest(BaseModel):
    event_id: int
    discord_user_id: str
    medal: str
    date_text: str = ""
    model_config = {"extra": "ignore"}


class BattleCupSubmitRequest(BaseModel):
    event_id: int
    discord_user_id: str
    tier: str
    model_config = {"extra": "ignore"}


class ScreenshotUploadRequest(BaseModel):
    event_id: int
    discord_user_id: str
    screenshot_type: str
    attachment_url: str
    model_config = {"extra": "ignore"}


class NotifyButtonRequest(BaseModel):
    event_id: int
    discord_user_id: str
    model_config = {"extra": "ignore"}


class DeclineButtonRequest(BaseModel):
    event_id: int
    discord_user_id: str
    model_config = {"extra": "ignore"}


class TentativeButtonRequest(BaseModel):
    event_id: int
    discord_user_id: str
    discord_username: Optional[str] = None
    model_config = {"extra": "ignore"}


class SavePositionsRequest(BaseModel):
    event_id: int
    discord_user_id: str
    positions: list[int]
    model_config = {"extra": "ignore"}


class SetPositionRequest(BaseModel):
    event_id: int
    discord_user_id: str
    position: int  # 1..5
    model_config = {"extra": "ignore"}


class RankFlowStateRequest(BaseModel):
    event_id: int
    discord_user_id: str
    model_config = {"extra": "ignore"}
