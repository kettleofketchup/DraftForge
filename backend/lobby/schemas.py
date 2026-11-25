"""Pydantic models for dota_lobby API responses (OpenAPI 1.0.0, /v1).

They ignore fields they do not know, so a newer dota_lobby does not break
DraftForge, and they accept `null` wherever the service may send it for a
list. Only the fields DraftForge uses are modelled.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr

from lobby import states


def _none_to_list(value: object) -> object:
    return [] if value is None else value


def _none_to_dict(value: object) -> object:
    return {} if value is None else value


IntList = Annotated[list[int], BeforeValidator(_none_to_list)]
StrList = Annotated[list[str], BeforeValidator(_none_to_list)]
StrDict = Annotated[dict[str, str], BeforeValidator(_none_to_dict)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ProblemError(_Model):
    message: str = ""
    location: str = ""
    value: Any = None


class PlayerView(_Model):
    account_id: int
    steam_id: str = ""
    captain: bool = False
    status: str = ""
    seat: str | None = None
    ready: bool = False
    invites_sent: int = 0
    last_invite_at: datetime | None = None
    invite_confirmed: bool = False


PlayerList = Annotated[list[PlayerView], BeforeValidator(_none_to_list)]


class TeamView(_Model):
    team_ref: str | None = None
    name: str | None = None
    players: PlayerList = Field(default_factory=list)


class TeamsView(_Model):
    radiant: TeamView = Field(default_factory=TeamView)
    dire: TeamView = Field(default_factory=TeamView)


class MemberView(_Model):
    account_id: int
    seat: str = ""


MemberList = Annotated[list[MemberView], BeforeValidator(_none_to_list)]


class HostSeatView(_Model):
    strategy: str | None = None
    confirmed: bool = False
    team: str | None = None


class MatchView(_Model):
    # 64-bit, sent as a string.
    match_id: str | None = None
    outcome: int | None = None
    outcome_name: str | None = None
    winner_side: str | None = None
    winner_team_ref: str | None = None
    scored: bool | None = None
    duration_seconds: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class LobbyView(_Model):
    """A lobby. `password` is set only by create-lobby and get-lobby."""

    id: str
    external_ref: str
    state: str
    state_reason: str | None = None
    seq: int = 0
    bot: str | None = None
    gc_lobby_id: str | None = None
    league_id: int | None = None
    league_node_id: int | None = None
    league_verified: bool | None = None
    name: str = ""
    game_mode: str | int | None = None
    region: str | int | None = None
    tv_delay_seconds: int | None = None
    visibility: str = ""
    allow_cheats: bool = False
    launch: str = ""
    ready_check: bool = False
    allow_short_handed: bool = False
    kick_strangers: bool = False
    admins: IntList = Field(default_factory=list)
    host_seat: HostSeatView | None = None
    teams: TeamsView = Field(default_factory=TeamsView)
    strangers: MemberList = Field(default_factory=list)
    # Outstanding invites as SteamID64 strings.
    pending_invites: StrList = Field(default_factory=list)
    match: MatchView | None = None
    launch_attempts: int = 0
    metadata: StrDict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None
    ended_at: datetime | None = None
    password: SecretStr | None = None

    @property
    def ended(self) -> bool:
        return self.state in states.SERVICE_TERMINAL_STATES


class CreateResult(_Model):
    lobby: LobbyView
    # True for dota_lobby's 200: an identical request for an active lobby
    # was already accepted, and this is that lobby.
    replayed: bool


class LobbySummary(_Model):
    """The lobby as carried in an event envelope."""

    id: str
    external_ref: str
    state: str
    bot: str | None = None
    gc_lobby_id: str | None = None
    league_id: int | None = None
    metadata: StrDict = Field(default_factory=dict)


class LobbyEvent(_Model):
    """One event, in the envelope webhooks and list-lobby-events both use."""

    id: str
    type: str
    seq: int
    occurred_at: datetime
    lobby: LobbySummary
    data: dict[str, Any] = Field(default_factory=dict)


class InviteSkip(_Model):
    account_id: int
    # in_lobby, pending_cooldown, cap or not_rostered
    reason: str


class InviteResult(_Model):
    invited: IntList = Field(default_factory=list)
    skipped: Annotated[list[InviteSkip], BeforeValidator(_none_to_list)] = Field(
        default_factory=list
    )


class LeagueHolder(_Model):
    bot: str
    source: str
    verified: bool = False
    refreshed_at: datetime | None = None


class LeagueBot(_Model):
    name: str
    stale: bool = False


class LeagueView(_Model):
    league_id: int
    name: str | None = None
    holders: Annotated[list[LeagueHolder], BeforeValidator(_none_to_list)] = Field(
        default_factory=list
    )
    bots: Annotated[list[LeagueBot], BeforeValidator(_none_to_list)] = Field(
        default_factory=list
    )
    holders_total: int = 0
    # Holders that could take a new lobby right now.
    holders_free: int = 0


class BotView(_Model):
    """A bot from GET /v1/bots, without its login, errors or token details."""

    name: str
    state: str
    ready: bool = False
    steam_id: str | None = None
    leagues: IntList = Field(default_factory=list)
    lobby: str | None = None
    lobby_stale: bool = False


class BotLeagueEntry(_Model):
    league_id: int
    source: str
    verified: bool = False
    refreshed_at: datetime | None = None
    stale: bool = False


class BotLeaguesRefresh(_Model):
    ok_at: datetime | None = None


class BotLeagues(_Model):
    leagues: Annotated[list[BotLeagueEntry], BeforeValidator(_none_to_list)] = Field(
        default_factory=list
    )
    refresh: BotLeaguesRefresh = Field(default_factory=BotLeaguesRefresh)


class LeagueRefreshItem(_Model):
    bot: str
    status: str


class LeagueRefreshResult(_Model):
    results: Annotated[list[LeagueRefreshItem], BeforeValidator(_none_to_list)] = Field(
        default_factory=list
    )
