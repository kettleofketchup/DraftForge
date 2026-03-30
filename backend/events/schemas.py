"""Pydantic schemas for event-related internal API data transfer.

These schemas serve as the contract between Django (producer) and
celery workers (consumer). They validate at both ends:

Django side (serializer):
    EventTaskSchema.model_validate(EventSerializer(event).data)
    -> catches if serializer output drifts from schema

Celery side (consumer):
    event = EventTaskSchema(**api_response)
    -> catches if API response drifts from what celery expects

When Django model fields change, update BOTH the serializer AND this
schema. The Pydantic ValidationError will catch any mismatch immediately.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas import UserSchema as TournamentUserSchema


class OrgProxy:
    """Proxy for event.organization attribute access in embed builders.

    Allows event.organization.name, .discord_server_id, .logo to work
    on both Django model instances and Pydantic EventTaskSchema.
    Also truthful (bool(proxy) == True) so `if event.organization:` works.
    """

    def __init__(self, pk: int, name: str, discord_server_id: str, logo: str):
        self.pk = pk
        self.name = name
        self.discord_server_id = discord_server_id
        self.logo = logo

    def __bool__(self):
        return True


class EventTaskSchema(BaseModel):
    """Validates: get_event_for_task() (app/views/internal.py)"""

    id: int
    name: str
    description: str = ""
    state: str
    scheduled_at: datetime
    signups_open_at: Optional[datetime] = None
    organization_id: int = 0  # the raw PK
    organization_name: str = ""
    organization_discord_server_id: str = ""
    organization_logo: str = ""
    event_repeater: Optional[int] = None
    event_repeater_id: Optional[int] = None
    event_repeater_name: Optional[str] = None
    tournament: Optional[int] = None
    tournament_name: str = ""
    tournament_league: Optional[int] = None

    @property
    def pk(self) -> int:
        return self.id

    @property
    def organization(self) -> OrgProxy:
        """Returns OrgProxy so event.organization.name works like Django."""
        return OrgProxy(
            pk=self.organization_id,
            name=self.organization_name,
            discord_server_id=self.organization_discord_server_id,
            logo=self.organization_logo,
        )

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


class DotaProfileSchema(BaseModel):
    """Validates: EventSignupSerializer.get_dota_profile() inline dict"""

    rank_status: str = "never"
    rank_medal: str = ""
    mmr: Optional[int] = None
    battle_cup_tier: Optional[int] = None
    rank_screenshot: Optional[str] = None
    battlecup_screenshot: Optional[str] = None
    positions: Optional[dict] = None

    model_config = {"extra": "ignore"}


class EventSignupSchema(BaseModel):
    """Validates: EventSignupSerializer (events/serializers.py)"""

    id: int
    event: int
    user: int  # user PK
    username: Optional[str] = None  # user.nickname
    user_avatar: Optional[str] = None
    user_data: Optional["TournamentUserSchema"] = None
    dota_profile: Optional[DotaProfileSchema] = None
    event_team: Optional[int] = None
    signup_type: str = "user"
    status: str = "rsvp"
    waitlist_position: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def display_name(self) -> str:
        if self.user_data:
            return self.user_data.display_name
        return self.username or f"User {self.user}"

    model_config = {"extra": "ignore"}


class RepeaterSubscriberSchema(BaseModel):
    """Validates: get_repeater_subscribers() (app/views/internal.py)"""

    user_pk: int
    discord_id: str
    org_user_pk: Optional[int] = None

    model_config = {"extra": "ignore"}


class EventTemplateSchema(BaseModel):
    """Validates: get_due_scheduled_events() nested template dict"""

    name: str = ""
    template_type: str = ""
    title: str = ""
    description: str = ""
    color: str = "#7289DA"
    channel_id: str = ""
    include_rsvp: bool = True

    model_config = {"extra": "ignore"}


class ScheduledEventDueSchema(BaseModel):
    """Validates: get_due_scheduled_events() (app/views/internal.py)"""

    pk: int
    is_recurring: bool = False
    next_post_at: Optional[str] = None
    template: EventTemplateSchema = EventTemplateSchema()

    model_config = {"extra": "ignore"}


def _rebuild_forward_refs() -> None:
    """Resolve deferred TournamentUserSchema reference (avoids circular import)."""
    from app.schemas import UserSchema as TournamentUserSchema  # noqa: F811

    EventSignupSchema.model_rebuild(
        _types_namespace={"TournamentUserSchema": TournamentUserSchema}
    )


_rebuild_forward_refs()
