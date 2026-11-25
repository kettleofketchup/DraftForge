"""Stable gate and note codes for Discord previews. Django-free."""

from typing import Literal

GateCode = Literal[
    "toggle_off",
    "no_channel",
    "no_signup_channel",
    "state_not_signups_open",
    "state_not_open_or_roll_call",
    "no_signup_post_yet",
    "no_discord_server",
    "start_in_past",
    "not_a_series",
    "no_recipients",
    "series_paused",
    "series_ended",
    "already_sent",
    "no_scheduled_event_yet",
]

NoteCode = Literal[
    "edits_refresh_embed_only",
    "fallback_drops_role_mentions",
    "signup_link_points_to_post",
    "unsaved_links",
    "sync_overwrites_description",
    "dm_per_subscriber",
    "shown_as_posted_when_signups_open",
    "fallback_replaces_notice",
    "signup_post_in_signup_channel",
    "notice_falls_back_if_signup_post_fails",
    "next_event_already_open_not_updated",
]
