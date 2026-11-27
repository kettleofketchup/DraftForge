from dataclasses import dataclass, replace
from typing import Literal

from discordbot.permissions.flags import PermissionFlag as F
from discordbot.permissions.schemas import ActionKind

PUBLIC_PREVIEW_ACTIONS: frozenset[ActionKind] = frozenset(ActionKind) - {
    ActionKind.ADMIN_CHANNEL_POST,
    ActionKind.SIGNUP_EDIT,
    ActionKind.ANNOUNCEMENT_EDIT,
}
EVENT_ACTIONS: frozenset[ActionKind] = frozenset(ActionKind) - {
    ActionKind.ADMIN_CHANNEL_POST,
    ActionKind.TEMPLATE_POST,
}


@dataclass(frozen=True)
class ActionProfile:
    kind: ActionKind
    scope: Literal["channel", "guild", "recipient", "unsupported"]
    required_all: tuple[F, ...]
    required_any: tuple[tuple[F, ...], ...]
    channel_types: frozenset[int]
    thread_send: bool


_TEXT_TYPES = frozenset({0, 5})
_MESSAGE_TYPES = frozenset({0, 5, 10, 11, 12})
_EMBED = (F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)
REGISTRY: dict[ActionKind, ActionProfile] = {
    kind: ActionProfile(kind, "channel", _EMBED, (), _TEXT_TYPES, False)
    for kind in (
        ActionKind.SIGNUP_FALLBACK,
        ActionKind.ANNOUNCEMENT,
        ActionKind.ATTENDANCE_REMINDER,
        ActionKind.PROFILE_REMINDER,
        ActionKind.NEW_EVENT_NOTICE,
        ActionKind.TEMPLATE_POST,
        ActionKind.ADMIN_CHANNEL_POST,
    )
}
REGISTRY[ActionKind.SIGNUP_CREATE] = ActionProfile(
    ActionKind.SIGNUP_CREATE,
    "channel",
    _EMBED,
    (),
    frozenset({0, 5, 15}),
    False,
)
REGISTRY[ActionKind.START_MENTION] = ActionProfile(
    ActionKind.START_MENTION,
    "channel",
    (F.VIEW_CHANNEL, F.SEND_MESSAGES, F.READ_MESSAGE_HISTORY),
    (),
    _MESSAGE_TYPES,
    True,
)
for _kind in (ActionKind.SIGNUP_EDIT, ActionKind.ANNOUNCEMENT_EDIT):
    REGISTRY[_kind] = ActionProfile(
        _kind, "channel", (F.VIEW_CHANNEL,), (), _MESSAGE_TYPES, False
    )
REGISTRY[ActionKind.SCHEDULED_EVENT_CREATE] = ActionProfile(
    ActionKind.SCHEDULED_EVENT_CREATE,
    "guild",
    (F.CREATE_EVENTS,),
    (),
    frozenset(),
    False,
)
for _kind in (ActionKind.SCHEDULED_EVENT_UPDATE, ActionKind.SCHEDULED_EVENT_DELETE):
    REGISTRY[_kind] = ActionProfile(
        _kind, "guild", (F.MANAGE_EVENTS,), (), frozenset(), False
    )
REGISTRY[ActionKind.MARK_INTERESTED] = ActionProfile(
    ActionKind.MARK_INTERESTED,
    "unsupported",
    (),
    (),
    frozenset(),
    False,
)
for _kind in (ActionKind.SIGNUP_REMINDER_DM, ActionKind.TOURNAMENT_DM):
    REGISTRY[_kind] = ActionProfile(_kind, "recipient", (), (), frozenset(), False)


def profile_for(
    kind: ActionKind,
    *,
    in_thread: bool,
    include_rsvp: bool,
    own_event: bool | None,
) -> ActionProfile:
    profile = REGISTRY[kind]
    if profile.thread_send and in_thread:
        profile = replace(
            profile,
            required_all=tuple(
                F.SEND_MESSAGES_IN_THREADS if flag == F.SEND_MESSAGES else flag
                for flag in profile.required_all
            ),
        )
    if kind == ActionKind.TEMPLATE_POST and include_rsvp:
        profile = replace(
            profile,
            required_all=(
                *profile.required_all,
                F.READ_MESSAGE_HISTORY,
                F.ADD_REACTIONS,
            ),
        )
    if (
        kind in (ActionKind.SCHEDULED_EVENT_UPDATE, ActionKind.SCHEDULED_EVENT_DELETE)
        and own_event is True
    ):
        profile = replace(
            profile, required_all=(), required_any=((F.CREATE_EVENTS, F.MANAGE_EVENTS),)
        )
    return profile
