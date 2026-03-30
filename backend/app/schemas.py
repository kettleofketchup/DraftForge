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

# Backward-compat re-exports (moved to discordbot/schemas.py with new names)
from discordbot.schemas import (  # noqa: F401
    DiscordEventStateSchema as DiscordEventState,
)
from discordbot.schemas import MessageLogSchema as MessageLogEntry  # noqa: F401
from discordbot.schemas import SyncDiscordStateSchema as SyncDiscordState  # noqa: F401


class UserSchema(BaseModel):
    """Shared user schema matching TournamentUserSerializer output.

    Reusable anywhere celery needs user data — signups, DMs, embeds, etc.
    """

    pk: int
    username: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    discordId: Optional[str] = None
    discordNickname: Optional[str] = None
    steam_account_id: Optional[int] = None
    avatarUrl: Optional[str] = None
    mmr: Optional[int] = None
    league_mmr: Optional[int] = None

    @property
    def display_name(self) -> str:
        return self.nickname or self.username or f"User {self.pk}"

    model_config = {"extra": "ignore"}


class TournamentParticipant(BaseModel):
    """User with Discord ID for tournament DM sending."""

    user_pk: int
    discord_id: str
    username: str = ""
    model_config = {"extra": "ignore"}


class TournamentTaskData(BaseModel):
    """Tournament data needed by Celery tasks."""

    id: int
    name: str
    state: str
    date_played: Optional[datetime] = None
    auto_create_hero_drafts: bool = False
    discord_send_draft_link: bool = False
    discord_send_herodraft_link: bool = False
    tournament_type: str = "double_elimination"
    draft_type: str = "shuffle"

    @property
    def pk(self) -> int:
        return self.id

    model_config = {"extra": "ignore"}


class GameWithoutHeroDraft(BaseModel):
    """Game that needs a hero draft auto-created."""

    id: int
    radiant_team_id: int
    radiant_team_name: str = ""
    dire_team_id: int
    dire_team_name: str = ""
    round: int = 1
    has_captains: bool = False
    model_config = {"extra": "ignore"}


# Backward compat -- use events.schemas for new code
from events.schemas import DotaProfileSchema  # noqa: F401, E402
from events.schemas import OrgProxy  # noqa: F401, E402
from events.schemas import EventSignupSchema as EventSignupData  # noqa: F401, E402
from events.schemas import EventTaskSchema as EventTaskData  # noqa: F401, E402
from events.schemas import EventTemplateSchema as EventTemplateData  # noqa: F401, E402
from events.schemas import (  # noqa: F401, E402
    RepeaterSubscriberSchema as RepeaterSubscriber,
)
from events.schemas import (  # noqa: F401, E402
    ScheduledEventDueSchema as ScheduledEventDue,
)
