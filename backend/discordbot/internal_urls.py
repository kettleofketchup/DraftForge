"""Bot-facing internal HTTP API.

These routes are mounted under ``api/internal/discord/`` from
``backend/urls.py`` and authenticated via ``X-Internal-Token``. The Discord
bot process posts to them through ``discordbot.internal_client.signup_actions``
so the backend stays the sole DB writer (the bot's overlay-fs cannot see
ORM writes made in the Daphne container).

View bodies live in ``discordbot/internal_signup_views.py``, ``discordbot/internal_voice_views.py``,
``discordbot/internal_dm_views.py`` and ``discordbot/internal_leadership_views.py``; this file is
only the URL table so the route layout matches the package that owns the
endpoints.
"""

from django.urls import URLPattern, path

from . import internal_dm_views as _dm_views
from . import internal_leadership_views as _leadership_views
from . import internal_signup_views as _signup_views
from . import internal_voice_views as _voice_views
from .activity_launch import activity_launch, activity_notification_invite

urlpatterns: list[URLPattern] = [
    path("activity-launch/", activity_launch, name="internal_activity_launch"),
    path(
        "activity-notification-invite/",
        activity_notification_invite,
        name="internal_activity_notification_invite",
    ),
    path(
        "signup-button/",
        _signup_views.signup_button,
        name="internal_discord_signup_button",
    ),
    path(
        "signup-modal-submit/",
        _signup_views.signup_modal_submit,
        name="internal_discord_signup_modal_submit",
    ),
    path(
        "rank-status-select/",
        _signup_views.rank_status_select,
        name="internal_discord_rank_status_select",
    ),
    path(
        "rank-medal-select/",
        _signup_views.rank_medal_select,
        name="internal_discord_rank_medal_select",
    ),
    path(
        "battle-cup-submit/",
        _signup_views.battle_cup_submit,
        name="internal_discord_battle_cup_submit",
    ),
    path(
        "screenshot-upload/",
        _signup_views.screenshot_upload,
        name="internal_discord_screenshot_upload",
    ),
    path(
        "notify-button/",
        _signup_views.notify_button,
        name="internal_discord_notify_button",
    ),
    path(
        "decline-button/",
        _signup_views.decline_button,
        name="internal_discord_decline_button",
    ),
    path(
        "tentative-button/",
        _signup_views.tentative_button,
        name="internal_discord_tentative_button",
    ),
    path(
        "save-positions/",
        _signup_views.save_positions,
        name="internal_discord_save_positions",
    ),
    path(
        "set-position/",
        _signup_views.set_position,
        name="internal_discord_set_position",
    ),
    path(
        "rank-flow-state/",
        _signup_views.rank_flow_state,
        name="internal_discord_rank_flow_state",
    ),
    path(
        "check-site-admin/",
        _signup_views.check_site_admin_view,
        name="internal_discord_check_site_admin",
    ),
    path(
        "reaction-signup/",
        _signup_views.reaction_signup_view,
        name="internal_discord_reaction_signup",
    ),
    path(
        "reaction-cancel/",
        _signup_views.reaction_cancel_view,
        name="internal_discord_reaction_cancel",
    ),
    path(
        "legacy-rsvp/set/",
        _signup_views.legacy_rsvp_set_view,
        name="internal_discord_legacy_rsvp_set",
    ),
    path(
        "legacy-rsvp/remove/",
        _signup_views.legacy_rsvp_remove_view,
        name="internal_discord_legacy_rsvp_remove",
    ),
    path(
        "legacy-event/create/",
        _signup_views.legacy_event_create_view,
        name="internal_discord_legacy_event_create",
    ),
    path(
        "voice/watched-channels/",
        _voice_views.voice_watched_channels,
        name="internal_discord_voice_watched_channels",
    ),
    path(
        "voice/state/",
        _voice_views.voice_state,
        name="internal_discord_voice_state",
    ),
    path(
        "voice/snapshot/",
        _voice_views.voice_snapshot,
        name="internal_discord_voice_snapshot",
    ),
    path("dms/claim/", _dm_views.dm_claim, name="internal_dm_claim"),
    path(
        "dms/<int:dm_id>/sending/",
        _dm_views.dm_sending,
        name="internal_dm_sending",
    ),
    path(
        "dms/<int:dm_id>/finalize/",
        _dm_views.dm_finalize,
        name="internal_dm_finalize",
    ),
    path("dms/click/", _dm_views.dm_click, name="internal_dm_click"),
    path(
        "leadership/review-click/",
        _leadership_views.review_click,
        name="internal_leadership_review_click",
    ),
]
