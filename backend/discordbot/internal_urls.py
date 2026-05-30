"""Bot-facing internal HTTP API.

These routes are mounted under ``api/internal/discord/`` from
``backend/urls.py`` and authenticated via ``X-Internal-Token``. The Discord
bot process posts to them through ``discordbot.internal_client.signup_actions``
so the backend stays the sole DB writer (the bot's overlay-fs cannot see
ORM writes made in the Daphne container).

View bodies live in ``discordbot/internal_signup_views.py``; this file is
only the URL table so the route layout matches the package that owns the
endpoints.
"""

from django.urls import URLPattern, path

from . import internal_signup_views as _signup_views

urlpatterns: list[URLPattern] = [
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
        "previous-rank-submit/",
        _signup_views.previous_rank_submit,
        name="internal_discord_previous_rank_submit",
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
]
