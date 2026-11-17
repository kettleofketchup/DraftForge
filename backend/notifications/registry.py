"""Catalogue of every member message DraftForge sends.

Pure Python with no Django imports: the TS/Zod exporter and the CI freshness
check load it with `python -I`. To add a message type, add a `MessageKey`
member and a `MessageType` entry, then run `just py::gen-message-types`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Channel(StrEnum):
    DM = "dm"
    EPHEMERAL = "ephemeral"
    CHANNEL_POST = "channel_post"


class Audience(StrEnum):
    SIGNUP = "signup"
    SUBSCRIBER = "subscriber"
    TOURNAMENT_PARTICIPANT = "tournament_participant"
    MATCH_PLAYER = "match_player"


class GroupKey(StrEnum):
    SIGNUP_RECEIPTS = "signup_receipts"
    ATTENDANCE = "attendance"
    ROSTER_CHANGES = "roster_changes"
    PRE_GAME_REMINDERS = "pre_game_reminders"
    SERIES_UPDATES = "series_updates"
    MATCH_LINKS = "match_links"
    CONDUCT = "conduct"


class MessageKey(StrEnum):
    RSVP_SIGNUP_RECEIPT = "rsvp.signup_receipt"
    RSVP_REACHABILITY_CHECK = "rsvp.reachability_check"
    RSVP_CONFIRM_REQUEST = "rsvp.confirm_request"
    RSVP_ESCALATION_NUDGE = "rsvp.escalation_nudge"
    EVENT_ATTENDANCE_REMINDER = "event.attendance_reminder"
    RSVP_PROMOTION = "rsvp.promotion"
    RSVP_ROSTER_CHANGE = "rsvp.roster_change"
    RSVP_DROP_NOTICE = "rsvp.drop_notice"
    RSVP_EVENT_CANCELLED = "rsvp.event_cancelled"
    RSVP_PRE_GAME_REMINDER = "rsvp.pre_game_reminder"
    EVENT_PROFILE_REMINDER = "event.profile_reminder"
    SERIES_SIGNUP_REMINDER = "series.signup_reminder"
    TOURNAMENT_DRAFT_LINK = "tournament.draft_link"
    TOURNAMENT_HERODRAFT_LINK = "tournament.herodraft_link"
    LOBBY_INFO = "lobby.info"


CONDUCT_GROUP = GroupKey.CONDUCT

MESSAGE_KEY_RE = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")
GROUP_KEY_RE = re.compile(r"^[a-z][a-z_]*$")


@dataclass(frozen=True, slots=True)
class MessageGroup:
    key: GroupKey
    label: str
    description: str
    opt_outable_default: bool
    essential_locked: bool = False


@dataclass(frozen=True, slots=True)
class MessageType:
    key: MessageKey
    group: GroupKey
    label: str
    description: str
    audience: Audience
    channels: tuple[Channel, ...]
    essential_default: bool = False
    essential_locked: bool = False
    urgent: bool = False


DM_OR_EPHEMERAL: tuple[Channel, ...] = (Channel.DM, Channel.EPHEMERAL)
DM_ONLY: tuple[Channel, ...] = (Channel.DM,)

GROUPS: tuple[MessageGroup, ...] = (
    MessageGroup(
        key=GroupKey.SIGNUP_RECEIPTS,
        label="Sign-up receipts",
        description="Confirmation that your sign-up for an event was received.",
        opt_outable_default=False,
    ),
    MessageGroup(
        key=GroupKey.ATTENDANCE,
        label="Attendance checks",
        description="Requests to confirm you will attend an event you signed up for.",
        opt_outable_default=False,
    ),
    MessageGroup(
        key=GroupKey.ROSTER_CHANGES,
        label="Roster changes",
        description="Changes to your place on an event roster or waitlist.",
        opt_outable_default=True,
    ),
    MessageGroup(
        key=GroupKey.PRE_GAME_REMINDERS,
        label="Pre-game reminders",
        description="Reminders shortly before an event you signed up for starts.",
        opt_outable_default=True,
    ),
    MessageGroup(
        key=GroupKey.SERIES_UPDATES,
        label="Series updates",
        description="News about recurring event series you subscribe to.",
        opt_outable_default=True,
    ),
    MessageGroup(
        key=GroupKey.MATCH_LINKS,
        label="Match links",
        description="Draft, hero draft and lobby details for matches you play in.",
        opt_outable_default=False,
    ),
    MessageGroup(
        key=GroupKey.CONDUCT,
        label="Conduct",
        description="Messages from organizers about conduct. Always delivered.",
        opt_outable_default=False,
        essential_locked=True,
    ),
)

MESSAGE_TYPES: tuple[MessageType, ...] = (
    MessageType(
        key=MessageKey.RSVP_SIGNUP_RECEIPT,
        group=GroupKey.SIGNUP_RECEIPTS,
        label="Sign-up receipt",
        description="Sent when you sign up for an event.",
        audience=Audience.SIGNUP,
        channels=DM_OR_EPHEMERAL,
    ),
    MessageType(
        key=MessageKey.RSVP_REACHABILITY_CHECK,
        group=GroupKey.SIGNUP_RECEIPTS,
        label="Reachability check",
        description=(
            "Sent on your first sign-up for an event with a ready check, "
            "to confirm DraftForge can reach you."
        ),
        audience=Audience.SIGNUP,
        channels=DM_OR_EPHEMERAL,
        essential_default=True,
    ),
    MessageType(
        key=MessageKey.RSVP_CONFIRM_REQUEST,
        group=GroupKey.ATTENDANCE,
        label="Confirm attendance",
        description="Asks you to confirm you will attend, with the no-show policy.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
        essential_default=True,
    ),
    MessageType(
        key=MessageKey.RSVP_ESCALATION_NUDGE,
        group=GroupKey.ATTENDANCE,
        label="Confirmation deadline",
        description="A final nudge when your attendance confirmation is overdue.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
        essential_default=True,
        urgent=True,
    ),
    MessageType(
        key=MessageKey.EVENT_ATTENDANCE_REMINDER,
        group=GroupKey.ATTENDANCE,
        label="Attendance reminder",
        description="Reminds you to confirm your attendance for an event.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.RSVP_PROMOTION,
        group=GroupKey.ROSTER_CHANGES,
        label="Promoted from waitlist",
        description=(
            "You moved off the waitlist into the roster. "
            "Withdraw at once if you cannot attend."
        ),
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
        essential_default=True,
        urgent=True,
    ),
    MessageType(
        key=MessageKey.RSVP_ROSTER_CHANGE,
        group=GroupKey.ROSTER_CHANGES,
        label="Roster change",
        description="Staff rejected, removed, moved or reinstated your sign-up.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.RSVP_DROP_NOTICE,
        group=GroupKey.ROSTER_CHANGES,
        label="Dropped from roster",
        description="You were dropped from the roster, for example after a missed check.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.RSVP_EVENT_CANCELLED,
        group=GroupKey.ROSTER_CHANGES,
        label="Event cancelled",
        description="An event you signed up for was cancelled.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.RSVP_PRE_GAME_REMINDER,
        group=GroupKey.PRE_GAME_REMINDERS,
        label="Pre-game reminder",
        description="Sent shortly before an event you are rostered for starts.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.EVENT_PROFILE_REMINDER,
        group=GroupKey.PRE_GAME_REMINDERS,
        label="Profile reminder",
        description="Asks you to complete your profile before an event.",
        audience=Audience.SIGNUP,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.SERIES_SIGNUP_REMINDER,
        group=GroupKey.SERIES_UPDATES,
        label="Series sign-up reminder",
        description="A new event in a series you subscribe to is open for sign-up.",
        audience=Audience.SUBSCRIBER,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.TOURNAMENT_DRAFT_LINK,
        group=GroupKey.MATCH_LINKS,
        label="Team draft link",
        description="The link to the team draft of a tournament you are in.",
        audience=Audience.TOURNAMENT_PARTICIPANT,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.TOURNAMENT_HERODRAFT_LINK,
        group=GroupKey.MATCH_LINKS,
        label="Hero draft link",
        description="The link to the hero draft of a match you play in.",
        audience=Audience.MATCH_PLAYER,
        channels=DM_ONLY,
    ),
    MessageType(
        key=MessageKey.LOBBY_INFO,
        group=GroupKey.MATCH_LINKS,
        label="Lobby details",
        description="The lobby name, password and your side for a match.",
        audience=Audience.MATCH_PLAYER,
        channels=DM_ONLY,
    ),
)


def validate_registry(
    groups: Iterable[MessageGroup], types: Iterable[MessageType]
) -> list[str]:
    errors: list[str] = []
    groups_by_key: dict[str, MessageGroup] = {}
    for group in groups:
        if group.key in groups_by_key:
            errors.append(f"duplicate group key {group.key!r}")
        if not GROUP_KEY_RE.match(group.key):
            errors.append(f"group {group.key!r}: bad key format")
        if not group.label.strip() or not group.description.strip():
            errors.append(f"group {group.key!r}: label and description required")
        if group.essential_locked and group.opt_outable_default:
            errors.append(f"group {group.key!r}: locked group cannot be opt-outable")
        groups_by_key[group.key] = group
    if CONDUCT_GROUP not in groups_by_key:
        errors.append(f"missing reserved group {CONDUCT_GROUP.value!r}")
    elif not groups_by_key[CONDUCT_GROUP].essential_locked:
        errors.append(f"group {CONDUCT_GROUP.value!r} must be essential_locked")

    seen: set[str] = set()
    for m in types:
        where = f"message {m.key!r}"
        if m.key in seen:
            errors.append(f"duplicate message key {m.key!r}")
        seen.add(m.key)
        if not MESSAGE_KEY_RE.match(m.key):
            errors.append(f"{where}: bad key format (want 'area.name')")
        if not m.label.strip():
            errors.append(f"{where}: empty label")
        if not m.description.strip():
            errors.append(f"{where}: empty description")
        if not m.channels:
            errors.append(f"{where}: no channels")
        elif len(set(m.channels)) != len(m.channels):
            errors.append(f"{where}: duplicate channels")
        if m.essential_locked and not m.essential_default:
            errors.append(f"{where}: essential_locked requires essential_default")
        group = groups_by_key.get(m.group)
        if group is None:
            errors.append(f"{where}: unknown group {m.group!r}")
            continue
        if group.essential_locked and not m.essential_locked:
            errors.append(f"{where}: every {group.key} type must be essential_locked")
        if set(m.channels) == {Channel.CHANNEL_POST} and group.opt_outable_default:
            errors.append(
                f"{where}: channel_post-only types cannot be in an opt-outable group"
            )
    return errors


_GROUPS_BY_KEY: dict[str, MessageGroup] = {g.key.value: g for g in GROUPS}
_TYPES_BY_KEY: dict[str, MessageType] = {m.key.value: m for m in MESSAGE_TYPES}


def get_message_type(key: str) -> MessageType:
    """Raises KeyError for an unknown key."""
    return _TYPES_BY_KEY[str(key)]


def get_group(key: str) -> MessageGroup:
    """Raises KeyError for an unknown key."""
    return _GROUPS_BY_KEY[str(key)]


def types_in_group(group: str) -> tuple[MessageType, ...]:
    return tuple(m for m in MESSAGE_TYPES if m.group == group)
