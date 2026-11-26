from dataclasses import dataclass
from datetime import datetime

from discordbot.permissions.actions import profile_for
from discordbot.permissions.effective import (
    THREAD_TYPES,
    channel_permissions,
    guild_permissions,
)
from discordbot.permissions.flags import BIT, labels
from discordbot.permissions.flags import PermissionFlag as F
from discordbot.permissions.schemas import (
    ActionKind,
    Blocker,
    ChannelSnap,
    Destination,
    GuildSnap,
    MemberSnap,
    Observation,
    PermissionCheckResult,
    ReasonCode,
)


@dataclass(frozen=True)
class ResolvedCheck:
    key: str
    action: ActionKind
    destination: Destination
    channel: ChannelSnap | None
    parent: ChannelSnap | None
    role_ids: tuple[str, ...]
    include_rsvp: bool
    reference_present: bool | None
    message_owned: bool | None
    event_creator_is_bot: bool | None
    reason_override: ReasonCode | None


@dataclass(frozen=True)
class SnapshotBundle:
    guild: GuildSnap | None
    member: MemberSnap | None
    observation: Observation | None
    error: ReasonCode | None
    retry_after: int | None


_EVENT_MODIFY = frozenset(
    {ActionKind.SCHEDULED_EVENT_UPDATE, ActionKind.SCHEDULED_EVENT_DELETE}
)
_EDIT = frozenset({ActionKind.SIGNUP_EDIT, ActionKind.ANNOUNCEMENT_EDIT})
_PING_ROLES = frozenset({ActionKind.SIGNUP_CREATE, ActionKind.ANNOUNCEMENT})
_UNCONFIGURED = frozenset(
    {"no_server_configured", "no_channel_configured", "pending_signup_post"}
)
_UNSUPPORTED = frozenset(
    {"unsupported_channel_type", "unsupported_endpoint", "unsupported_signup_transport"}
)


def evaluate(
    check: ResolvedCheck, bundle: SnapshotBundle, now: datetime
) -> PermissionCheckResult:
    channel = check.channel
    in_thread = channel is not None and channel.type in THREAD_TYPES
    profile = profile_for(
        check.action,
        in_thread=in_thread,
        include_rsvp=check.include_rsvp,
        own_event=check.event_creator_is_bot,
    )
    result = PermissionCheckResult(
        key=check.key,
        action=check.action,
        status="unknown",
        destination=check.destination,
        required_all=[flag.value for flag in profile.required_all],
        required_any=[[flag.value for flag in group] for group in profile.required_any],
        retry_after_seconds=bundle.retry_after,
    )
    if profile.scope == "recipient":
        result.destination = Destination(kind="dm", source="recipient")
        result.status = "not_applicable"
        return result
    if profile.scope == "unsupported":
        result.status, result.reason = "unsupported", "unsupported_endpoint"
        return result
    if profile.scope == "guild":
        result.destination = Destination(kind="guild", source="guild")
    reason = check.reason_override or bundle.error
    if reason is not None:
        result.reason = reason
        result.status = (
            "unconfigured"
            if reason in _UNCONFIGURED
            else "unsupported"
            if reason in _UNSUPPORTED
            else "unknown"
        )
        return result
    if bundle.guild is None:
        result.status, result.reason = "unconfigured", "no_server_configured"
        return result
    if check.action in _EVENT_MODIFY and check.reference_present is not True:
        result.status = "unconfigured"
        result.blockers.append(Blocker(code="missing_reference"))
        return result
    if check.action == ActionKind.START_MENTION and check.reference_present is not True:
        result.status, result.reason = "unconfigured", "pending_signup_post"
        return result
    if check.action in _EDIT and check.reference_present is not True:
        result.status = "unconfigured"
        result.blockers.append(Blocker(code="missing_reference"))
        return result
    if profile.scope == "channel":
        if channel is None:
            if check.destination.channel_id is None:
                result.status, result.reason = "unconfigured", "no_channel_configured"
            else:
                result.reason = "resource_unavailable"
            return result
        if channel.type not in profile.channel_types:
            result.status = "unsupported"
            result.reason = (
                "unsupported_signup_transport"
                if check.action == ActionKind.SIGNUP_CREATE and channel.type in (0, 5)
                else "unsupported_channel_type"
            )
            return result
        if channel.id != check.destination.channel_id:
            result.reason = "malformed_snapshot"
            return result
    observation = bundle.observation
    if (
        observation is None
        or observation.observed_at.tzinfo is None
        or observation.expires_at.tzinfo is None
        or not observation.observed_at <= now < observation.expires_at
    ):
        result.reason = "malformed_snapshot"
        return result
    result.checked_at, result.expires_at = (
        observation.observed_at,
        observation.expires_at,
    )
    if bundle.member is None:
        result.reason = "bot_unavailable"
        return result
    effective = (
        channel_permissions(bundle.guild, bundle.member, channel, check.parent, now)
        if profile.scope == "channel" and channel is not None
        else guild_permissions(bundle.guild, bundle.member, now)
    )
    if not effective.complete or effective.bits is None or effective.base_bits is None:
        result.reason = "malformed_snapshot"
        return result
    current = effective.bits
    result.granted = labels(current)
    result.effective_permissions = str(current)
    result.raw_permissions = str(effective.base_bits)
    result.base_granted = labels(effective.base_bits)
    result.bypass = effective.bypass
    if check.action in _PING_ROLES:
        for role_id in dict.fromkeys(check.role_ids):
            role = bundle.guild.roles.get(role_id)
            if role is None:
                result.blockers.append(Blocker(code="role_missing", role_id=role_id))
            elif not role.mentionable:
                if F.MENTION_EVERYONE.value not in result.required_all:
                    result.required_all.append(F.MENTION_EVERYONE.value)
                if not current & BIT[F.MENTION_EVERYONE]:
                    result.blockers.append(
                        Blocker(
                            code="role_not_mentionable",
                            role_id=role_id,
                            missing=[F.MENTION_EVERYONE.value],
                        )
                    )
    result.missing = [
        flag for flag in result.required_all if not current & BIT[F(flag)]
    ]
    unmet_alternatives = [
        group
        for group in result.required_any
        if not any(current & BIT[F(flag)] for flag in group)
    ]
    if effective.timeout_until is not None:
        result.expires_at = min(result.expires_at, effective.timeout_until)
        stripped = [
            flag for flag in result.missing if effective.base_bits & BIT[F(flag)]
        ]
        for group in unmet_alternatives:
            if any(effective.base_bits & BIT[F(flag)] for flag in group):
                stripped.extend(group)
        if stripped:
            result.blockers.append(
                Blocker(
                    code="communication_timeout", missing=list(dict.fromkeys(stripped))
                )
            )
    if channel is not None and profile.scope == "channel":
        if check.action == ActionKind.SIGNUP_CREATE and channel.available_tags_required:
            result.blockers.append(Blocker(code="forum_requires_tag"))
        if in_thread:
            meta = channel.thread_meta
            if meta is None or meta.private != (channel.type == 12):
                result.reason = "malformed_snapshot"
            else:
                if meta.private and meta.bot_is_member is not True:
                    result.blockers.append(Blocker(code="private_thread_access"))
                if meta.archived:
                    result.blockers.append(Blocker(code="thread_archived"))
                if meta.locked:
                    result.blockers.append(Blocker(code="thread_locked"))
    ownership_unknown = (
        check.action in _EDIT
        and check.message_owned is not True
        or check.action in _EVENT_MODIFY
        and check.event_creator_is_bot is None
        and not current & BIT[F.MANAGE_EVENTS]
    )
    if ownership_unknown:
        result.reason = "malformed_snapshot"
    codes = {blocker.code for blocker in result.blockers}
    if "forum_requires_tag" in codes:
        result.status = "unsupported"
    elif result.reason is not None or codes & {
        "role_missing",
        "private_thread_access",
        "thread_archived",
        "thread_locked",
    }:
        result.status = "unknown"
    elif result.missing or unmet_alternatives:
        result.status = "missing_permissions"
    else:
        result.status = "verified"
    return result
