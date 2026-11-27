"""Pure send predicates shared by the Discord tasks, the views and the preview.

Every gate reads only attributes present on both ``Event`` and
``EventTaskSchema``; state that lives elsewhere is passed in. A gate reports
every failing reason; each task reacts only to the reasons it enforces.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Literal

from events.constants import EventState
from events.discord.channels import (
    attendance_reminder_channel,
    new_event_channel,
    profile_reminder_channel,
)
from events.discord.preview_codes import GateCode
from events.utils import starts_in_future

if TYPE_CHECKING:
    from discordbot.schemas import DiscordEventStateSchema
    from events.discord.embeds import EmbedEvent
    from events.models import EventRepeater

AnnouncementBranch = Literal[
    "signup_post_only", "signup_post_and_notice", "fallback_signup_post", "none"
]
DestinationType = Literal["channel", "forum_thread", "dm", "reply", "scheduled_event"]

OPEN_OR_ROLL_CALL: frozenset[str] = frozenset(
    {EventState.SIGNUPS_OPEN, EventState.ROLL_CALL}
)


@dataclass
class GateResult:
    would_send: bool
    reasons: list[GateCode] = field(default_factory=list)


@dataclass(frozen=True)
class Destination:
    type: DestinationType
    channel_id: str | None
    thread_name: str | None = None
    fallback_channel_id: str | None = None
    reply_to_message_id: str | None = None


def _result(reasons: list[GateCode]) -> GateResult:
    return GateResult(would_send=not reasons, reasons=reasons)


def announcement_send_state() -> EventState:
    return EventState.SIGNUPS_OPEN


def initial_state_for_new_event(open_signups: bool) -> EventState:
    return EventState.SIGNUPS_OPEN if open_signups else EventState.UPCOMING


def _signup_available(event: "EmbedEvent") -> bool:
    return bool(event.discord_post_signups and event.discord_post_signups_channel_id)


def _announcement_available(event: "EmbedEvent") -> bool:
    return bool(event.discord_announcement and event.discord_announcement_channel_id)


def announcement_branch(event: "EmbedEvent") -> AnnouncementBranch:
    signup = _signup_available(event)
    announcement = _announcement_available(event)
    if signup and announcement:
        return "signup_post_and_notice"
    if signup:
        return "signup_post_only"
    if announcement:
        return "fallback_signup_post"
    return "none"


def signup_post_destination(event: "EmbedEvent") -> Destination | None:
    branch = announcement_branch(event)
    if branch == "none":
        return None
    if branch == "fallback_signup_post":
        return Destination(
            type="channel", channel_id=event.discord_announcement_channel_id
        )
    fallback = (
        event.discord_announcement_channel_id
        if branch == "signup_post_and_notice"
        else None
    )
    thread_name = (event.discord_event_title or event.name)[:100] or None
    return Destination(
        type="forum_thread" if thread_name else "channel",
        channel_id=event.discord_post_signups_channel_id,
        thread_name=thread_name,
        fallback_channel_id=fallback,
    )


def signup_post_channel(discord_state: "DiscordEventStateSchema") -> str | None:
    if discord_state.signup_channel_type == "forum":
        return discord_state.signup_thread_id or discord_state.signup_channel_id
    if discord_state.signup_channel_type == "text":
        return discord_state.signup_channel_id
    return discord_state.signup_thread_id or discord_state.signup_channel_id


SIGNUPS_OPEN_ONLY: frozenset[str] = frozenset({EventState.SIGNUPS_OPEN})


def _state_reason(event: "EmbedEvent", allowed: frozenset[str]) -> list[GateCode]:
    if event.state in allowed:
        return []
    if allowed == SIGNUPS_OPEN_ONLY:
        return ["state_not_signups_open"]
    return ["state_not_open_or_roll_call"]


def _fired(already_fired: bool) -> list[GateCode]:
    return ["already_sent"] if already_fired else []


def signup_post_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if announcement_branch(event) == "none":
        if not event.discord_post_signups and not manual:
            reasons.append("toggle_off")
        elif not event.discord_post_signups_channel_id:
            reasons.append("no_signup_channel")
    reasons += _state_reason(event, frozenset({announcement_send_state()}))
    reasons += _fired(already_fired)
    return _result(reasons)


def announcement_notice_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if not event.discord_announcement and not manual:
        reasons.append("toggle_off")
    if not event.discord_announcement_channel_id:
        reasons.append("no_channel")
    reasons += _state_reason(event, frozenset({announcement_send_state()}))
    reasons += _fired(already_fired)
    return _result(reasons)


def _channel_reminder_gate(
    event: "EmbedEvent",
    channel: str,
    toggle: bool,
    states: frozenset[str],
    already_fired: bool,
    manual: bool,
) -> GateResult:
    reasons: list[GateCode] = []
    if not toggle and not manual:
        reasons.append("toggle_off")
    if not channel:
        reasons.append("no_channel")
    reasons += _state_reason(event, states)
    reasons += _fired(already_fired)
    return _result(reasons)


def attendance_reminder_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    return _channel_reminder_gate(
        event,
        attendance_reminder_channel(event),
        event.discord_confirm_attendance,
        OPEN_OR_ROLL_CALL,
        already_fired,
        manual,
    )


def profile_reminder_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    return _channel_reminder_gate(
        event,
        profile_reminder_channel(event),
        event.discord_profile_reminder,
        SIGNUPS_OPEN_ONLY,
        already_fired,
        manual,
    )


def start_mention_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if not event.discord_start_mention and not manual:
        reasons.append("toggle_off")
    reasons += _state_reason(event, OPEN_OR_ROLL_CALL)
    if not (
        discord_state
        and discord_state.signup_posted
        and discord_state.signup_message_id
    ):
        reasons.append("no_signup_post_yet")
    reasons += _fired(already_fired)
    return _result(reasons)


def new_event_post_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if not new_event_channel(event):
        reasons.append("no_channel")
    reasons += _fired(already_fired)
    return _result(reasons)


def scheduled_event_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if not event.discord_create_event and not manual:
        reasons.append("toggle_off")
    if not event.organization.discord_server_id:
        reasons.append("no_discord_server")
    if not starts_in_future(event.scheduled_at):
        reasons.append("start_in_past")
    reasons += _fired(already_fired)
    return _result(reasons)


def scheduled_event_sync_gate(
    event: "EmbedEvent",
    *,
    scheduled_event_message_id: str | None,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if not event.discord_sync_signups and not manual:
        reasons.append("toggle_off")
    if not scheduled_event_message_id:
        reasons.append("no_scheduled_event_yet")
    reasons += _fired(already_fired)
    return _result(reasons)


def signup_reminder_gate(
    event: "EmbedEvent",
    *,
    discord_state: "DiscordEventStateSchema | None" = None,
    already_fired: bool = False,
    manual: bool = False,
) -> GateResult:
    reasons: list[GateCode] = []
    if not event.discord_signup_reminder and not manual:
        reasons.append("toggle_off")
    if not event.event_repeater_id:
        reasons.append("not_a_series")
    if not discord_state or not discord_state.has_discord_event:
        reasons.append("no_discord_server")
    reasons += _state_reason(event, SIGNUPS_OPEN_ONLY)
    reasons += _fired(already_fired)
    return _result(reasons)


def repeater_generates(repeater: "EventRepeater", today: date) -> GateResult:
    reasons: list[GateCode] = []
    if not repeater.is_active:
        reasons.append("series_paused")
    elif repeater.ends_at and repeater.ends_at < today:
        reasons.append("series_ended")
    return _result(reasons)
