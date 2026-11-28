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

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from discordbot.delivery_types import (
    ChannelKind,
    DeliveryFailure,
    DeliveryReceipt,
    FailureCategory,
    FailurePhase,
)

DiscordId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]


class SyncDiscordStateSchema(BaseModel):
    """Validates: get_sync_discord_state() (app/views/internal.py)"""

    active_events: list[dict]
    existing_logs: list[list]  # [[source, source_id], ...]
    events_with_signup: list[int]
    events_with_scheduled: list[int]
    events_with_recent_attempt: list[int]
    events_with_signup_blocked: list[int] = []

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
    """Validates: get_discord_event_state() (app/views/internal.py).

    Channel-routing fields determine how the embed-edit PATCH is addressed:

    - **text channel** (`signup_channel_type == "text"`): edit at
      `PATCH /channels/{signup_channel_id}/messages/{signup_message_id}`.
      `signup_thread_id` is None.
    - **forum channel** (`signup_channel_type == "forum"`): Discord
      auto-creates a thread to hold the post; the starter message's
      effective "channel" for edits IS the thread. Edit at
      `PATCH /channels/{signup_thread_id}/messages/{signup_message_id}`.
      `signup_channel_id` is the parent forum channel (kept for context).

    Legacy rows may have `signup_channel_type` unset (empty/None). In that
    case `_send_signup_update_impl` falls back to the legacy heuristic
    (`thread_id or channel_id`) and logs a `legacy_channel_type` warning.
    """

    has_discord_event: bool = False
    discord_event_pk: Optional[int] = None
    scheduled_event_id: Optional[str] = None
    signup_posted: bool = False
    signup_message_id: Optional[str] = None
    signup_channel_id: Optional[str] = None
    signup_thread_id: Optional[str] = None
    signup_channel_type: Optional[str] = None  # "text" | "forum" | None (legacy)
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
    discord_username: str | None = None
    model_config = {"extra": "ignore"}


class SignupModalSubmitRequest(BaseModel):
    event_id: int
    discord_user_id: str
    # Game the modal was built for; the handler rejects a mismatch with the
    # event's current game. None (or omitted) marks the fallback modal, which
    # is rejected once the event belongs to a game with its own handler.
    game_type: int | None = None
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
    discord_username: str | None = None
    model_config = {"extra": "ignore"}


class TentativeButtonRequest(BaseModel):
    event_id: int
    discord_user_id: str
    discord_username: str | None = None
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


# ---------------------------------------------------------------------------
# Bot-control internal-API request schemas (validated server-side in
# discordbot/internal_signup_views.py). These cover the legacy ScheduledEvent
# / RSVP flow and the /event slash command admin check.
# ---------------------------------------------------------------------------


class CheckSiteAdminRequest(BaseModel):
    discord_user_id: str
    model_config = {"extra": "ignore"}


class ReactionSignupRequest(BaseModel):
    discord_message_id: str
    discord_user_id: str
    model_config = {"extra": "ignore"}


class ReactionCancelRequest(BaseModel):
    discord_message_id: str
    discord_user_id: str
    model_config = {"extra": "ignore"}


class LegacyRsvpSetRequest(BaseModel):
    discord_message_id: str
    discord_user_id: str
    status: Literal["yes", "maybe", "no"]
    discord_username: str
    model_config = {"extra": "ignore"}


class LegacyRsvpRemoveRequest(BaseModel):
    discord_message_id: str
    discord_user_id: str
    model_config = {"extra": "ignore"}


class LegacyEventCreateRequest(BaseModel):
    name: str
    description: str
    channel_id: str
    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Bot-control internal-API response schemas. Pure transport contracts (not
# domain output of any shared handler), so they live with the bot.
# ---------------------------------------------------------------------------


class SiteAdminCheckResponse(BaseModel):
    is_admin: bool = False
    is_linked: bool = False
    error: str | None = None
    model_config = {"extra": "ignore"}


class ReactionResponse(BaseModel):
    success: bool = False
    detail: str = ""
    model_config = {"extra": "ignore"}


class LegacyRsvpResponse(BaseModel):
    success: bool = False
    error: str | None = None
    event_name: str | None = None
    model_config = {"extra": "ignore"}


class LegacyEventCreateResponse(BaseModel):
    success: bool = False
    error: str | None = None
    event_id: int | None = None
    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Voice presence feed (``discordbot/internal_voice_views.py``).
# ---------------------------------------------------------------------------


class WatchedChannelSchema(BaseModel):
    guild_id: DiscordId
    channel_id: DiscordId
    event_ids: list[int]
    model_config = {"extra": "ignore"}


class WatchedChannelsResponse(BaseModel):
    channels: list[WatchedChannelSchema] = []
    ttl_seconds: int = 60
    available: bool = True
    model_config = {"extra": "ignore"}


class VoiceStateRequest(BaseModel):
    guild_id: DiscordId
    discord_user_id: DiscordId
    before_channel_id: DiscordId | None = None
    after_channel_id: DiscordId | None = None
    model_config = {"extra": "ignore"}


class VoiceSnapshotChannel(BaseModel):
    channel_id: DiscordId
    member_ids: list[DiscordId] = Field(default_factory=list, max_length=5000)
    model_config = {"extra": "ignore"}

    @field_validator("member_ids")
    @classmethod
    def _dedupe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class VoiceSnapshotRequest(BaseModel):
    guild_id: DiscordId
    channels: list[VoiceSnapshotChannel] = Field(max_length=100)
    missing_channel_ids: list[DiscordId] = []
    model_config = {"extra": "ignore"}


class VoicePresenceResponse(BaseModel):
    success: bool = False
    detail: str = ""
    events: int = 0
    joined: int = 0
    left: int = 0
    confirmed: int = 0
    unknown_users: int = 0
    not_signed_up: int = 0
    model_config = {"extra": "ignore"}


# --- DM ledger (discordbot/internal_dm_views.py) -----------------------------
# Imported before the app registry is ready, so the DiscordDM enums are mirrored
# as Literals; test_internal_dm_views checks they match.

DMKindValue = Literal[
    "signup_reminder",
    "tournament_draft_link",
    "tournament_herodraft_link",
    "lobby_info",
    "signup_confirmation",
    "test_notification",
]
DMStatusValue = Literal[
    "pending",
    "sent",
    "failed",
    "unknown",
    "skipped_test_mode",
    "skipped_no_discord",
    "skipped_disabled",
]
DMSubjectValue = Literal["event", "tournament", "game_lobby"]
DMErrorClassValue = Literal[
    "pre_send", "rate_limit_timeout", "before_send_failed", "permanent"
]
LedgerToken = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class DMClaimBody(BaseModel):
    kind: DMKindValue
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    claim_token: LedgerToken
    discord_user_id: DiscordId | Literal[""] = ""
    recipient_user_id: int | None = None
    organization_id: int | None = None
    subject_type: DMSubjectValue | None = None
    subject_id: int | None = None
    tournament_log_id: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    has_components: bool = False
    initial_status: DMStatusValue | None = None
    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def _subject_pair(self) -> DMClaimBody:
        if (self.subject_type is None) != (self.subject_id is None):
            raise ValueError("subject_type and subject_id go together")
        return self


class DMSendingBody(BaseModel):
    claim_token: LedgerToken
    model_config = {"extra": "ignore"}


class DMFinalizeBody(BaseModel):
    claim_token: LedgerToken
    status: DMStatusValue
    error_class: DMErrorClassValue | None = None
    discord_channel_id: DiscordId | Literal[""] = ""
    discord_message_id: DiscordId | None = None
    http_status: Annotated[int, Field(ge=100, le=599)] | None = None
    error_code: int | None = None
    error: str = ""
    model_config = {"extra": "ignore"}


class DMClickBody(BaseModel):
    discord_message_id: DiscordId
    discord_user_id: DiscordId
    model_config = {"extra": "ignore"}


class DMLedgerRowResponse(BaseModel):
    id: int
    status: DMStatusValue
    attempts: int = 0
    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Signup delivery reservations (``discordbot/internal_signup_delivery_views.py``).
# ---------------------------------------------------------------------------

PositiveId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
Generation = Annotated[int, Field(strict=True, ge=0)]
HttpStatus = Annotated[int, Field(strict=True, ge=100, le=599)]
StrictCode = Annotated[int, Field(strict=True)]
BeginOutcomeName = Literal[
    "reserved",
    "already_delivered",
    "in_flight",
    "deferred",
    "exhausted",
    "uncertain",
    "stale_generation",
]
CompletionOutcomeName = Literal["recorded", "idempotent", "stale"]


class SignupDeliveryBeginRequest(BaseModel):
    event_id: PositiveId
    generation: Generation | None = None
    model_config = {"extra": "forbid"}


class SignupDeliverySendingRequest(BaseModel):
    event_id: PositiveId
    generation: Generation
    attempt_token: UUID
    log_id: PositiveId
    model_config = {"extra": "forbid"}


class SignupDeliveryReceiptPayload(BaseModel):
    parent_channel_id: str
    message_id: str
    thread_id: str | None
    kind: ChannelKind
    model_config = {"extra": "forbid"}

    def to_receipt(self) -> DeliveryReceipt:
        return DeliveryReceipt.from_json(self.model_dump(mode="json"))


class SignupDeliveryFailurePayload(BaseModel):
    phase: FailurePhase
    category: FailureCategory
    status: HttpStatus | None = None
    code: StrictCode | None = None
    model_config = {"extra": "forbid"}

    def to_failure(self) -> DeliveryFailure:
        return DeliveryFailure(self.phase, self.category, self.status, self.code)


class SignupDeliveryCompleteRequest(BaseModel):
    event_id: PositiveId
    generation: Generation
    attempt_token: UUID
    outcome: Literal["delivered", "failed", "uncertain"]
    receipt: SignupDeliveryReceiptPayload | None = None
    failure: SignupDeliveryFailurePayload | None = None
    log_id: PositiveId | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _evidence_matches_outcome(self) -> Self:
        if self.outcome == "delivered":
            if self.receipt is None or self.failure is not None:
                raise ValueError("delivered requires a receipt and no failure")
            self.receipt.to_receipt()
        elif self.receipt is not None:
            raise ValueError("only delivered accepts a receipt")
        return self


class SignupDeliveryBeginReply(BaseModel):
    outcome: BeginOutcomeName
    generation: Generation
    attempt_token: str | None = None
    attempt: PositiveId | None = None
    next_attempt_at: datetime | None = None
    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def _reservation_has_identity(self) -> Self:
        if self.outcome == "reserved":
            if self.attempt_token is None or self.attempt is None:
                raise ValueError("a reservation requires an attempt identity")
            UUID(self.attempt_token)
        elif self.attempt_token is not None or self.attempt is not None:
            raise ValueError("only a reservation carries an attempt identity")
        return self


class SignupDeliverySendingReply(BaseModel):
    outcome: Literal["ok", "stale"]
    model_config = {"extra": "ignore"}


class SignupDeliveryCompleteReply(BaseModel):
    outcome: CompletionOutcomeName
    persisted: Annotated[bool, Field(strict=True)]
    next_attempt_at: datetime | None = None
    state: str | None = None
    model_config = {"extra": "ignore"}


class SignupDeliveryBlockedReply(BaseModel):
    event_ids: list[PositiveId]
    model_config = {"extra": "ignore"}
