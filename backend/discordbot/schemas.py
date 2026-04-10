"""Pydantic schemas for Discord bot API data transfer.

These schemas validate data returned by internal API endpoints
consumed by the Discord bot (via celery tasks or direct HTTP calls).
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
