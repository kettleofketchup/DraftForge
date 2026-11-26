from dataclasses import dataclass
from datetime import datetime
from typing import Literal


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
