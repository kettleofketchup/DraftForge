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

This module also owns the RESPONSE schemas for the Discord bot's signup-flow
internal API (``SignupActionResponse``, ``RankFlowStateResponse``). Those
shapes are the public contract of the ``handle_*`` functions in
``events.discord.handlers``, so they belong here rather than in the bot's
transport package. Request bodies for the same endpoints live in
``discordbot/schemas.py`` because they validate Discord-button payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from app.schemas import TournamentUserSchema


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


class PositionPriorities(BaseModel):
    """Per-role priority rating matching CustomUser.positions (PositionsModel).
    0 = "don't play this role", 1..5 = Favorite → Least Favorite (same scale
    the edit-profile PositionForm uses). Submitted by the web signup modal.
    """

    model_config = ConfigDict(extra="forbid")

    carry: int = Field(default=0, ge=0, le=5)
    mid: int = Field(default=0, ge=0, le=5)
    offlane: int = Field(default=0, ge=0, le=5)
    soft_support: int = Field(default=0, ge=0, le=5)
    hard_support: int = Field(default=0, ge=0, le=5)


class SignupInputPatch(BaseModel):
    """Profile patch sent by web/Discord callers to apply_signup_input.

    All fields optional - callers send only what changed. Validation rules:
    - rank_status must be one of the allowed literals (event-policy gating
      lives in apply_signup_input, not here).
    - positions accepts EITHER a priority dict (web modal: per-role 0..5,
      same shape as edit-profile) OR a list[int] in {1..5} (Discord adapter
      legacy: list of role numbers to mark as preferred, mapped to priority=1).
      apply_signup_input normalizes both into a PositionPriorities for storage.
    - battle_cup_tier in {1..8}.
    - URL fields are validated for shape + extension in apply_signup_input
      so message strings stay consistent with the Discord vocabulary.

    `extra="forbid"` rejects unknown keys so the API surface is strict.
    """

    model_config = ConfigDict(extra="forbid")

    unverified_friend_id: Optional[str] = Field(default=None, max_length=20)
    positions: Optional[PositionPriorities | list[int]] = None
    rank_status: Optional[Literal["active", "previous", "never"]] = None
    rank_medal: Optional[str] = Field(default=None, max_length=64)
    battle_cup_tier: Optional[int] = Field(default=None, ge=1, le=8)
    rank_screenshot: Optional[str] = Field(default=None, max_length=500)
    battlecup_screenshot: Optional[str] = Field(default=None, max_length=500)

    @field_validator("positions")
    @classmethod
    def _validate_positions_range(cls, v):
        # PositionPriorities already validates 0..5 per field; only the legacy
        # list[int] form needs the role-number range check here.
        if v is None or isinstance(v, PositionPriorities):
            return v
        for p in v:
            if p < 1 or p > 5:
                raise ValueError(f"position {p} out of range 1..5")
        return v


# ---------------------------------------------------------------------------
# Bot-API response schemas — contract of events.discord.handlers.handle_*.
# Validated client-side in discordbot/internal_client/signup_actions.py and
# returned by the views in discordbot/internal_signup_views.py.
# ---------------------------------------------------------------------------


class SignupActionResponse(BaseModel):
    """All bot-facing handler return dicts share this shape.

    Different handlers populate different subsets; consumer code branches on
    ``action`` and reads only the relevant fields. Used as the union envelope
    so a single pydantic model can validate every signup-flow response.
    """

    # Common fields
    action: str | None = None  # signed_up | needs_modal | needs_screenshot |
    # needs_rank_details | needs_rank_status | error | tentative | declined |
    # not_signed_up | already_declined | already_tentative | positions_saved |
    # position_set
    status: str | None = None  # SignupStatus value when action == "signed_up"
    message: str | None = None  # human-readable for error / not_signed_up / etc.

    # signup_modal_submit / signup_button: needs_modal payload
    game_type: int | None = None
    prefill: dict | None = None
    require_steam_id: bool | None = None
    require_rank_screenshot: bool | None = None
    require_battlecup_screenshot: bool | None = None
    min_mmr: int | None = None
    allow_active_mmr: bool | None = None
    allow_previous_rank: bool | None = None
    allow_battlecup_rating: bool | None = None

    # rank_medal_select / battle_cup_submit: needs_screenshot payload
    screenshot_type: str | None = None
    medal: str | None = None
    tier: str | None = None

    # notify_button
    subscribed: bool | None = None

    # screenshot_upload
    success: bool | None = None
    signed_up: bool | None = None

    # save_positions
    positions: list[int] | None = None

    model_config = {"extra": "ignore"}


class RankFlowStateResponse(BaseModel):
    """Response of /api/internal/discord/rank-flow-state/.

    Used by the legacy pos_confirm flow in bot.py to construct the next
    RankDetailsView. ``error``/``message`` populated only on lookup failure;
    otherwise the rank_status + require_screenshot + min_mmr fields drive UI.
    """

    rank_status: str | None = None  # "active" | "previous" | "never"
    require_screenshot: bool = False
    min_mmr: int | None = None
    error: str | None = None  # set when the lookup fails (e.g. event_not_found / no_org_user)
    message: str | None = None
    model_config = {"extra": "ignore"}


def _rebuild_forward_refs() -> None:
    """Resolve deferred TournamentUserSchema reference (avoids circular import)."""
    from app.schemas import TournamentUserSchema  # noqa: F811

    EventSignupSchema.model_rebuild(
        _types_namespace={"TournamentUserSchema": TournamentUserSchema}
    )


_rebuild_forward_refs()
