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


# ---------------------------------------------------------------------------
# Internal signup-API response schema (validated client-side in
# app/internal_client/signup_actions.py).
# ---------------------------------------------------------------------------


class SignupActionResponse(BaseModel):
    """All bot-facing handler return dicts share this shape.

    Different handlers populate different subsets; consumer code branches on
    ``action`` and reads only the relevant fields. Used as the union envelope
    so a single pydantic model can validate every signup-flow response.
    """

    # Common fields
    action: Optional[str] = None  # signed_up | needs_modal | needs_screenshot |
    # needs_rank_details | needs_rank_status | error | tentative | declined |
    # not_signed_up | already_declined | already_tentative | positions_saved |
    # position_set
    status: Optional[str] = None  # SignupStatus value when action == "signed_up"
    message: Optional[str] = None  # human-readable for error / not_signed_up / etc.

    # signup_modal_submit / signup_button: needs_modal payload
    game_type: Optional[int] = None
    prefill: Optional[dict] = None
    require_steam_id: Optional[bool] = None
    require_rank_screenshot: Optional[bool] = None
    require_battlecup_screenshot: Optional[bool] = None
    min_mmr: Optional[int] = None
    allow_active_mmr: Optional[bool] = None
    allow_previous_rank: Optional[bool] = None
    allow_battlecup_rating: Optional[bool] = None

    # rank_medal_select / battle_cup_submit: needs_screenshot payload
    screenshot_type: Optional[str] = None
    medal: Optional[str] = None
    tier: Optional[str] = None

    # notify_button
    subscribed: Optional[bool] = None

    # screenshot_upload
    success: Optional[bool] = None
    signed_up: Optional[bool] = None

    # save_positions
    positions: Optional[list[int]] = None

    model_config = {"extra": "ignore"}


class RankFlowStateResponse(BaseModel):
    """Response of /api/internal/discord/rank-flow-state/.

    Used by the legacy pos_confirm flow in bot.py to construct the next
    RankDetailsView. ``error``/``message`` populated only on lookup failure;
    otherwise the rank_status + require_screenshot + min_mmr fields drive UI.
    """

    rank_status: Optional[str] = None  # "active" | "previous" | "never"
    require_screenshot: bool = False
    min_mmr: Optional[int] = None
    error: Optional[str] = None  # set when the lookup fails (e.g. event_not_found / no_org_user)
    message: Optional[str] = None
    model_config = {"extra": "ignore"}
