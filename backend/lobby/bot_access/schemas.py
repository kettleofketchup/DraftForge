"""Game-neutral wire contract for lobby bot league access.

Django-free so ``export_bot_access_schema.py`` runs under ``python -I``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BotStatus = Literal["available", "busy", "connecting", "offline", "unknown"]
AccessState = Literal["verified", "unverified", "missing", "unknown"]
AccessNote = Literal["allowed_unverified", "not_rechecked"]
ServiceStatus = Literal[
    "ok",
    "unsupported",
    "disabled",
    "not_configured",
    "league_not_linked",
    "unavailable",
    "error",
]
RowRefresh = Literal["ok", "failed", "not_ready"]
RefreshOutcome = Literal["ok", "unavailable", "timed_out", "not_supported_upstream"]
Roster = Literal["all", "holders"]

HTTPS_PATTERN = r"^https://"


class Response(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class BotIdentity(Response):
    kind: str
    value: str
    profile_url: str | None = Field(default=None, pattern=HTTPS_PATTERN)


class BotAccessRow(Response):
    position: int
    identity: BotIdentity | None
    status: BotStatus | None
    access: AccessState
    access_note: AccessNote | None = None
    access_checked_at: datetime | None = None
    refresh: RowRefresh | None = None


class PlatformLink(Response):
    kind: Literal["league_admin_portal"]
    url: str = Field(pattern=HTTPS_PATTERN)


class ServiceState(Response):
    status: ServiceStatus
    code: str | None = None
    retryable: bool = False


class BotAccessSnapshot(Response):
    game_type: int | None
    supported: bool
    provider: str
    external_league_id: str | None
    service: ServiceState
    bots: list[BotAccessRow]
    held_count: int
    league_link: PlatformLink | None = None
    refresh_outcome: RefreshOutcome | None = None
    roster: Roster = "all"
    checked_at: datetime


class BotAccessApi(BaseModel):
    snapshot: BotAccessSnapshot
