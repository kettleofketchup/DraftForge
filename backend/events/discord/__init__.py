"""
Event <-> Discord integration layer.

Embed builders (pure functions) and dispatch functions that check config flags
and send Celery tasks for Discord notifications.

Re-exports all public symbols for backward compatibility — existing code can
continue to ``from events.discord import build_announcement_embed`` etc.
"""

from events.discord.components import build_announcement_components
from events.discord.dispatch import (
    notify_create_discord_event,
    notify_event_announced,
    notify_mark_interested,
    notify_new_event,
    notify_signup_changed,
    notify_sync_signups,
)
from events.discord.embeds import (
    COLOR_ANNOUNCEMENT,
    COLOR_NEW_EVENT,
    COLOR_PROFILE,
    COLOR_REMINDER,
    COLOR_SIGNUP,
    _discord_timestamp,
    _event_url,
    _signup_counts,
    build_announcement_embed,
    build_announcement_embeds,
    build_announcement_notice,
    build_announcement_v2,
    build_attendance_reminder_embed,
    build_new_event_embed,
    build_profile_reminder_embed,
    build_signup_reminder_embed,
    build_signup_update_embed,
    build_subscriber_dm_embed,
)
from events.discord.handlers import (
    _check_deadlock_profile_complete,
    _check_dota_profile_complete,
    _get_org_user,
    handle_battle_cup_submit,
    handle_decline_button,
    handle_notify_button,
    handle_previous_rank_submit,
    handle_rank_medal_select,
    handle_rank_status_select,
    handle_screenshot_upload,
    handle_signup_button,
    handle_signup_modal_submit,
    handle_tentative_button,
)
from events.discord.reactions import handle_reaction_cancel, handle_reaction_signup

__all__ = [
    # embeds
    "COLOR_ANNOUNCEMENT",
    "COLOR_SIGNUP",
    "COLOR_REMINDER",
    "COLOR_PROFILE",
    "COLOR_NEW_EVENT",
    "_discord_timestamp",
    "_event_url",
    "_signup_counts",
    "build_announcement_embed",
    "build_announcement_embeds",
    "build_announcement_notice",
    "build_announcement_v2",
    "build_signup_update_embed",
    "build_new_event_embed",
    "build_signup_reminder_embed",
    "build_attendance_reminder_embed",
    "build_profile_reminder_embed",
    "build_subscriber_dm_embed",
    # components
    "build_announcement_components",
    # dispatch
    "notify_event_announced",
    "notify_signup_changed",
    "notify_new_event",
    "notify_create_discord_event",
    "notify_sync_signups",
    "notify_mark_interested",
    # handlers
    "_check_dota_profile_complete",
    "_check_deadlock_profile_complete",
    "_get_org_user",
    "handle_signup_button",
    "handle_signup_modal_submit",
    "handle_rank_medal_select",
    "handle_rank_status_select",
    "handle_previous_rank_submit",
    "handle_battle_cup_submit",
    "handle_screenshot_upload",
    "handle_notify_button",
    "handle_decline_button",
    "handle_tentative_button",
    # reactions
    "handle_reaction_signup",
    "handle_reaction_cancel",
]
