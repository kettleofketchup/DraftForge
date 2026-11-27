from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass(frozen=True)
class RoleSnap:
    id: str
    permissions: int
    mentionable: bool
    managed: bool


@dataclass(frozen=True)
class Overwrite:
    id: str
    type: Literal[0, 1]
    allow: int
    deny: int


@dataclass(frozen=True)
class ThreadMeta:
    archived: bool
    locked: bool
    private: bool
    bot_is_member: bool | None


@dataclass(frozen=True)
class ChannelSnap:
    id: str
    guild_id: str
    type: int
    name: str
    parent_id: str | None
    overwrites: tuple[Overwrite, ...]
    flags: int
    thread_meta: ThreadMeta | None
    available_tags_required: bool


@dataclass(frozen=True)
class GuildSnap:
    id: str
    owner_id: str
    roles: dict[str, RoleSnap]


@dataclass(frozen=True)
class MemberSnap:
    user_id: str
    role_ids: tuple[str, ...]
    communication_disabled_until: datetime | None | Literal["malformed"]


@dataclass(frozen=True)
class Observation:
    observed_at: datetime
    expires_at: datetime


class ActionKind(StrEnum):
    SIGNUP_CREATE = "signup_create"
    SIGNUP_FALLBACK = "signup_fallback"
    ANNOUNCEMENT = "announcement"
    ATTENDANCE_REMINDER = "attendance_reminder"
    PROFILE_REMINDER = "profile_reminder"
    NEW_EVENT_NOTICE = "new_event_notice"
    START_MENTION = "start_mention"
    SIGNUP_EDIT = "signup_edit"
    ANNOUNCEMENT_EDIT = "announcement_edit"
    SCHEDULED_EVENT_CREATE = "scheduled_event_create"
    SCHEDULED_EVENT_UPDATE = "scheduled_event_update"
    SCHEDULED_EVENT_DELETE = "scheduled_event_delete"
    MARK_INTERESTED = "mark_interested"
    SIGNUP_REMINDER_DM = "signup_reminder_dm"
    TOURNAMENT_DM = "tournament_dm"
    TEMPLATE_POST = "template_post"
    ADMIN_CHANNEL_POST = "admin_channel_post"


CheckStatus = Literal[
    "verified",
    "missing_permissions",
    "unconfigured",
    "unknown",
    "unsupported",
    "not_applicable",
]
ReasonCode = Literal[
    "no_server_configured",
    "no_channel_configured",
    "bot_unavailable",
    "credential_unavailable",
    "forbidden_read",
    "resource_unavailable",
    "rate_limited",
    "network_error",
    "malformed_snapshot",
    "pending_signup_post",
    "unsupported_channel_type",
    "unsupported_endpoint",
]
BlockerCode = Literal[
    "missing_reference",
    "forum_requires_tag",
    "communication_timeout",
    "role_not_mentionable",
    "role_missing",
    "thread_archived",
    "thread_locked",
    "private_thread_access",
]
Snowflake = Annotated[str, Field(pattern=r"^[0-9]{17,20}$")]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Response(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class PermissionCheckIn(Request):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    action: ActionKind
    channel_id: Snowflake | None
    role_ids: list[Snowflake] = Field(default_factory=list, max_length=25)
    include_rsvp: bool = False
    fallback: bool = Field(default_factory=bool)


class PermissionChecksRequest(Request):
    refresh: bool = False
    checks: list[PermissionCheckIn] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_keys(self) -> Self:
        if len({check.key for check in self.checks}) != len(self.checks):
            raise ValueError("Check keys must be unique")
        return self


class Destination(Response):
    kind: Literal["channel", "thread", "guild", "dm", "none"]
    channel_id: str | None = None
    parent_id: str | None = None
    name: str | None = None
    channel_type: int | None = None
    source: (
        Literal["configured", "fallback", "posted", "prospective", "guild", "recipient"]
        | None
    ) = None


class Blocker(Response):
    code: BlockerCode
    detail: str | None = None
    role_id: str | None = None
    missing: list[str] = Field(default_factory=list)


class PermissionCheckResult(Response):
    key: str
    action: ActionKind
    status: CheckStatus
    destination: Destination
    required_all: list[str] = Field(default_factory=list)
    required_any: list[list[str]] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    granted: list[str] | None = None
    effective_permissions: str | None = None
    raw_permissions: str | None = None
    base_granted: list[str] | None = None
    bypass: Literal["owner", "administrator"] | None = None
    blockers: list[Blocker] = Field(default_factory=list)
    reason: ReasonCode | None = None
    checked_at: datetime | None = None
    expires_at: datetime | None = None
    retry_after_seconds: int | None = None
    refresh_state: Literal["fresh", "cached", "coalesced", "throttled"] | None = None


class PermissionChecksResponse(Response):
    guild_id: str | None
    checks: list[PermissionCheckResult]


@dataclass(frozen=True)
class ResolvedCheckInput:
    key: str
    action: ActionKind
    destination_source: Literal[
        "configured", "fallback", "posted", "prospective", "guild", "recipient"
    ]
    channel_id: str | None
    role_ids: tuple[str, ...] = ()
    include_rsvp: bool = False
    reference_present: bool | None = None
    message_id: str | None = None
    scheduled_event_id: str | None = None


class PermissionChecksApi(BaseModel):
    request: PermissionChecksRequest
    response: PermissionChecksResponse
