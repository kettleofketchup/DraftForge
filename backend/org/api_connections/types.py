from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ConfigRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class CredentialField(ConfigRecord):
    location: Literal["query", "body"]
    key: Annotated[str, Field(min_length=1, max_length=128)]


class SafeHttpRequest(ConfigRecord):
    url: str = Field(repr=False)
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, JsonValue] = Field(default_factory=dict, repr=False)
    body: dict[str, JsonValue] | None = Field(default=None, repr=False)
    auth: Literal["none", "bearer", "api_key_header", "api_key_field"] = "none"
    credential: str | None = Field(default=None, repr=False)
    credential_origin: str | None = Field(default=None, repr=False)
    credential_field: CredentialField | None = None
    idempotency_key: (
        Annotated[
            str,
            Field(
                pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
            ),
        ]
        | None
    ) = None


class SafeHttpResponse(ConfigRecord):
    status: int
    data: JsonValue = Field(repr=False)
    bytes_received: int


class ResponseMapping(ConfigRecord):
    list_path: str = ""
    player_id_path: str = "id"
    player_id_type: Literal["steam_account_id", "steam64", "discord_id"] = (
        "steam_account_id"
    )
    mmr_path: str = "mmr"


class PaginationConfig(ConfigRecord):
    kind: Literal["none", "page", "cursor"] = "none"
    start: Annotated[int, Field(ge=0, le=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=500)] = 500
    has_more_path: str | None = None
    next_cursor_path: str | None = None


class MmrPushConfig(ConfigRecord):
    path: str = "/api/v1/organizations/{org_id}/mmr"
    query: dict[str, JsonValue] = Field(default_factory=dict)
    body: dict[str, JsonValue] | None = None
    credential_field: CredentialField | None = None


class MmrPullConfig(ConfigRecord):
    path: str = "/"
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, JsonValue] = Field(default_factory=dict)
    body: dict[str, JsonValue] | None = None
    credential_field: CredentialField | None = None
    request_mode: Literal["org", "member_batches", "per_member"] = "org"
    acknowledge_per_member: bool = False
    mapping: ResponseMapping = Field(default_factory=ResponseMapping)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)


class ConnectionConfig(ConfigRecord):
    name: Annotated[str, Field(min_length=1, max_length=64)] = "Connection"
    enabled: bool = False
    inbound_enabled: bool = False
    mmr_push_enabled: bool = False
    mmr_pull_enabled: bool = False
    promotion_push_enabled: bool = False
    operations: list[
        Literal[
            "mmr:read",
            "mmr:write",
            "promotion:import",
            "promotion:read",
            "promotion:write",
        ]
    ] = Field(default_factory=list)
    outbound_base_url: Annotated[str, Field(max_length=2048)] = ""
    outbound_auth: Literal["none", "bearer", "api_key_header", "api_key_field"] = "none"
    mmr_push_config: MmrPushConfig = Field(default_factory=MmrPushConfig)
    mmr_pull_config: MmrPullConfig = Field(default_factory=MmrPullConfig)
    game_type: Annotated[int, Field(ge=0, le=32767)] | None = None
    overwrite_policy: Literal["missing_only", "unverified_only", "replace"] = (
        "missing_only"
    )
    mark_verified: bool = False
    interval_minutes: Annotated[int, Field(ge=15, le=10080)] | None = None


@dataclass(frozen=True, slots=True)
class SnapshotMember:
    org_user_id: int
    steam_account_id: int | None
    discord_id: str | None
    revision: int = 0


@dataclass(frozen=True, slots=True)
class MemberSnapshot:
    organization_id: int
    game_type: int
    members: tuple[SnapshotMember, ...] = ()


@dataclass(frozen=True, slots=True)
class MappedRow:
    page: int
    index: int
    player_id: str | None
    mmr: int | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MappedPage:
    rows: tuple[MappedRow, ...]
    has_more: bool = False
    next_cursor: str | int | None = None


@dataclass(frozen=True, slots=True)
class StepResult:
    state: str
    continuation: bool
    error_code: str | None = None
