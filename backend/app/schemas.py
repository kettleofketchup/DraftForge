"""Pydantic schemas for internal API data transfer.

These schemas serve as the contract between Django (producer) and
celery workers (consumer). They validate at both ends:

Django side (serializer):
    EventTaskData.model_validate(EventSerializer(event).data)
    → catches if serializer output drifts from schema

Celery side (consumer):
    event = EventTaskData(**api_response)
    → catches if API response drifts from what celery expects

When Django model fields change, update BOTH the serializer AND this
schema. The Pydantic ValidationError will catch any mismatch immediately.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EventTaskData(BaseModel):
    """Event data needed by celery tasks. Matches EventSerializer + org extras."""

    id: int
    name: str
    description: str = ""
    state: str
    scheduled_at: datetime
    signups_open_at: Optional[datetime] = None
    organization: int
    organization_name: str = ""
    organization_discord_server_id: str = ""
    event_repeater: Optional[int] = None
    event_repeater_id: Optional[int] = None
    event_repeater_name: Optional[str] = None
    tournament: Optional[int] = None
    tournament_name: str = ""
    tournament_league: Optional[int] = None

    # Counts
    signup_count: int = 0
    confirmed_count: int = 0
    max_players: Optional[int] = None
    min_players: Optional[int] = None

    # Tournament config
    tournament_type: str = "single_elimination"
    draft_type: str = "shuffle"
    game_type: int = 1
    people_per_team: int = 5
    number_of_teams: Optional[int] = None

    # Discord config
    discord_create_event: bool = False
    discord_sync_signups: bool = False
    discord_event_title: str = ""
    discord_event_description: str = ""
    discord_event_info: str = ""
    discord_signup_reminder: bool = False
    discord_signup_reminder_hours: int = 24
    discord_confirm_attendance: bool = False
    discord_confirm_attendance_hours: int = 2
    discord_profile_reminder: bool = False
    discord_profile_reminder_hours: int = 24
    discord_mark_interested: bool = False
    discord_post_signups: bool = False
    discord_post_signups_channel_id: str = ""
    discord_announcement: bool = False
    discord_announcement_channel_id: str = ""
    discord_announcement_hours: int = 24
    discord_announcement_role_ids: list = []
    discord_signup_role_ids: list = []
    discord_subscriber_dm: bool = False
    discord_subscriber_dm_hours: int = 24

    # Config
    timezone: str = "America/New_York"
    roll_call_enabled: bool = False

    model_config = {"extra": "ignore"}  # ignore extra fields from serializer


class SyncDiscordState(BaseModel):
    """Bulk state returned by get_sync_discord_state endpoint."""

    active_events: list[dict]
    existing_logs: list[list]  # [[source, source_id], ...]
    events_with_signup: list[int]
    events_with_scheduled: list[int]
    events_with_recent_attempt: list[int]

    model_config = {"extra": "ignore"}


class MessageLogEntry(BaseModel):
    """Single DiscordMessageLog entry from search endpoint."""

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


class DiscordEventState(BaseModel):
    """Discord event state for a single event."""

    has_discord_event: bool = False
    discord_event_pk: Optional[int] = None
    scheduled_event_id: Optional[str] = None
    signup_posted: bool = False
    fired_actions: list[str] = []
    has_dms: bool = False

    model_config = {"extra": "ignore"}


class RepeaterSubscriber(BaseModel):
    """Subscriber info for DM sending."""

    user_pk: int
    discord_id: str
    org_user_pk: int

    model_config = {"extra": "ignore"}


class ScheduledEventDue(BaseModel):
    """ScheduledEvent due for posting."""

    pk: int
    is_recurring: bool = False
    next_post_at: Optional[str] = None
    template: dict = {}

    model_config = {"extra": "ignore"}
