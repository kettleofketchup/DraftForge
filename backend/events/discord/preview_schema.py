"""Request and response models of the Discord message preview. Django-free."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from discordbot.payload_schema import DiscordMessage
from events.discord.preview_codes import GateCode, NoteCode

PreviewKind = Literal[
    "scheduled_event",
    "scheduled_event_sync",
    "signup_reminder",
    "profile_reminder",
    "attendance_reminder",
    "start_mention",
    "signup_post",
    "announcement_notice",
    "new_event_post",
]
PreviewStatus = Literal["ok", "needs_input", "unavailable"]
PreviewDestinationType = Literal[
    "channel", "forum_thread", "dm", "reply", "scheduled_event"
]


class _Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventContext(_Forbid):
    type: Literal["event"]
    event_id: int


class NewEventContext(_Forbid):
    type: Literal["new_event"]
    organization_id: int


class SeriesOneOffContext(_Forbid):
    type: Literal["series_one_off"]
    repeater_id: int


class RepeaterContext(_Forbid):
    type: Literal["repeater"]
    repeater_id: int


class NewRepeaterContext(_Forbid):
    type: Literal["new_repeater"]
    organization_id: int


class OrgDefaultsContext(_Forbid):
    type: Literal["org_defaults"]
    organization_id: int


PreviewContext = Annotated[
    EventContext
    | NewEventContext
    | SeriesOneOffContext
    | RepeaterContext
    | NewRepeaterContext
    | OrgDefaultsContext,
    Field(discriminator="type"),
]


class DiscordPreviewRequest(_Forbid):
    kind: PreviewKind
    context: PreviewContext
    values: dict[str, Any] = {}
    open_signups: bool = False


class Gate(BaseModel):
    would_send: bool
    reasons: list[GateCode] = []


class PreviewDestination(BaseModel):
    type: PreviewDestinationType
    channel_id: str | None = None
    thread_name: str | None = None
    fallback_channel_id: str | None = None
    reply_to_message_id: str | None = None


class Variant(BaseModel):
    code: Literal["current_post"]
    messages: list[DiscordMessage] = []


class ScheduledEventLocation(BaseModel):
    location: str


class ScheduledEventPreview(BaseModel):
    name: str
    description: str
    scheduled_start_time: str
    scheduled_end_time: str | None = None
    entity_metadata: ScheduledEventLocation


class Mentions(BaseModel):
    users: dict[str, str] = {}


class DiscordPreviewResponse(BaseModel):
    kind: PreviewKind
    status: PreviewStatus
    missing: list[str] = []
    saved: bool
    gate: Gate
    destination: PreviewDestination | None = None
    messages: list[DiscordMessage] = []
    variants: list[Variant] = []
    scheduled_event: ScheduledEventPreview | None = None
    notes: list[NoteCode] = []
    note_args: dict[str, str] = {}
    mentions: Mentions = Mentions()


class DiscordPreviewApi(BaseModel):
    request: DiscordPreviewRequest
    response: DiscordPreviewResponse
