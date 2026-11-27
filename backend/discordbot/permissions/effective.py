from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from discordbot.permissions.flags import (
    ALL_KNOWN,
    BIT,
    CHANNEL_SCOPED_MASK,
    PermissionFlag,
)
from discordbot.permissions.schemas import ChannelSnap, GuildSnap, MemberSnap

THREAD_TYPES: frozenset[int] = frozenset({10, 11, 12})

_VIEW = BIT[PermissionFlag.VIEW_CHANNEL]
_SEND = BIT[PermissionFlag.SEND_MESSAGES]
_SEND_IN_THREADS = BIT[PermissionFlag.SEND_MESSAGES_IN_THREADS]
_ADMINISTRATOR = BIT[PermissionFlag.ADMINISTRATOR]
_SEND_DEPENDENTS = (
    BIT[PermissionFlag.SEND_TTS_MESSAGES]
    | BIT[PermissionFlag.EMBED_LINKS]
    | BIT[PermissionFlag.ATTACH_FILES]
    | BIT[PermissionFlag.MENTION_EVERYONE]
)
_TIMEOUT_KEEP = _VIEW | BIT[PermissionFlag.READ_MESSAGE_HISTORY]
_MALFORMED = "malformed_snapshot"

Bypass = Literal["owner", "administrator"]


@dataclass(frozen=True)
class Effective:
    complete: bool
    bits: int | None
    base_bits: int | None
    bypass: Bypass | None
    timeout_until: datetime | None
    incomplete_reason: str | None


@dataclass(frozen=True)
class _Base:
    everyone: int
    roles: int
    role_ids: frozenset[str]
    bypass: Bypass | None
    timeout_until: datetime | None


_INCOMPLETE = Effective(False, None, None, None, None, _MALFORMED)


def _base(guild: GuildSnap, member: MemberSnap, now: datetime) -> _Base | None:
    everyone = guild.roles.get(guild.id)
    if everyone is None or any(
        role_id not in guild.roles for role_id in member.role_ids
    ):
        return None
    until = member.communication_disabled_until
    if until == "malformed" or (isinstance(until, datetime) and until.tzinfo is None):
        return None
    permissions = [
        everyone.permissions,
        *(guild.roles[r].permissions for r in member.role_ids),
    ]
    if any(bits < 0 for bits in permissions):
        return None
    roles = 0
    for bits in permissions[1:]:
        roles |= bits
    combined = everyone.permissions | roles
    bypass: Bypass | None = None
    if member.user_id == guild.owner_id:
        bypass = "owner"
    elif combined & _ADMINISTRATOR:
        bypass = "administrator"
    active = bypass is None and isinstance(until, datetime) and until > now
    return _Base(
        everyone.permissions,
        roles,
        frozenset(member.role_ids),
        bypass,
        until if active else None,
    )


def _finish(base: _Base, pre_timeout: int) -> Effective:
    bits = pre_timeout & _TIMEOUT_KEEP if base.timeout_until else pre_timeout
    return Effective(True, bits, pre_timeout, base.bypass, base.timeout_until, None)


def guild_permissions(guild: GuildSnap, member: MemberSnap, now: datetime) -> Effective:
    base = _base(guild, member, now)
    if base is None:
        return _INCOMPLETE
    combined = base.everyone | base.roles
    if base.bypass:
        combined |= ALL_KNOWN
    return _finish(base, combined)


def _overwrites_valid(channel: ChannelSnap) -> bool:
    seen: set[tuple[int, str]] = set()
    for overwrite in channel.overwrites:
        key = (overwrite.type, overwrite.id)
        if (
            overwrite.type not in (0, 1)
            or overwrite.allow < 0
            or overwrite.deny < 0
            or key in seen
        ):
            return False
        seen.add(key)
    return True


def channel_permissions(
    guild: GuildSnap,
    member: MemberSnap,
    channel: ChannelSnap,
    parent: ChannelSnap | None,
    now: datetime,
) -> Effective:
    base = _base(guild, member, now)
    if base is None or channel.guild_id != guild.id:
        return _INCOMPLETE
    is_thread = channel.type in THREAD_TYPES
    source = channel
    if is_thread:
        if (
            parent is None
            or parent.id != channel.parent_id
            or parent.guild_id != guild.id
            or parent.type in THREAD_TYPES
        ):
            return _INCOMPLETE
        source = parent
    if not _overwrites_valid(source):
        return _INCOMPLETE

    combined = base.everyone | base.roles
    if base.bypass:
        return _finish(base, combined | ALL_KNOWN)

    bits = combined
    role_allow = role_deny = 0
    member_overwrite = None
    for overwrite in source.overwrites:
        if overwrite.type == 0 and overwrite.id == guild.id:
            bits = (bits & ~overwrite.deny) | overwrite.allow
        elif overwrite.type == 0 and overwrite.id in base.role_ids:
            role_allow |= overwrite.allow
            role_deny |= overwrite.deny
        elif overwrite.type == 1 and overwrite.id == member.user_id:
            member_overwrite = overwrite
    bits = (bits & ~role_deny) | role_allow
    if member_overwrite is not None:
        bits = (bits & ~member_overwrite.deny) | member_overwrite.allow

    channel_bits = bits & CHANNEL_SCOPED_MASK
    if not channel_bits & _VIEW:
        channel_bits = 0
    elif not channel_bits & (_SEND_IN_THREADS if is_thread else _SEND):
        channel_bits &= ~_SEND_DEPENDENTS
    return _finish(base, channel_bits | (combined & ~CHANNEL_SCOPED_MASK))
