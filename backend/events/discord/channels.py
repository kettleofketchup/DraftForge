"""Discord channel for each event post: its own setting, else the announcement channel."""

from typing import Protocol


class _ChannelConfig(Protocol):
    discord_announcement_channel_id: str
    discord_confirm_attendance_channel_id: str
    discord_profile_reminder_channel_id: str
    discord_new_event_channel_id: str


def attendance_reminder_channel(event: _ChannelConfig) -> str:
    return (
        event.discord_confirm_attendance_channel_id
        or event.discord_announcement_channel_id
    )


def profile_reminder_channel(event: _ChannelConfig) -> str:
    return (
        event.discord_profile_reminder_channel_id
        or event.discord_announcement_channel_id
    )


def new_event_channel(event: _ChannelConfig) -> str:
    return event.discord_new_event_channel_id or event.discord_announcement_channel_id


def reminder_channel(event: _ChannelConfig, reminder_type: str) -> str:
    if reminder_type == "confirm_attendance":
        return attendance_reminder_channel(event)
    if reminder_type == "profile_reminder":
        return profile_reminder_channel(event)
    return event.discord_announcement_channel_id
