from django.urls import path

from .activity import activity_session
from .activity_config import activity_config
from .activity_views import activity_drafts, activity_views
from .services.channels import get_discord_channels
from .services.install import (
    check_discord_bot_status,
    discord_install_callback,
    discord_install_link,
)
from .services.permissions import organization_permission_checks
from .services.roles import get_discord_roles
from .services.users import (
    get_discord_members,
    get_discord_voice_channel_activity,
    get_organization_discord_members,
    get_user_guilds,
    refresh_discord_members,
    search_discord_members,
)
from .views import discord_interactions

urlpatterns = [
    path(
        "organizations/<int:pk>/permission-checks/",
        organization_permission_checks,
        name="discord-permission-checks",
    ),
    path("activity/config/", activity_config, name="discord-activity-config"),
    path("activity/session/", activity_session, name="discord-activity-session"),
    path("activity/drafts/", activity_drafts, name="discord-activity-drafts"),
    path("activity/views/", activity_views, name="discord-activity-views"),
    path(
        "get_discord_activity/",
        get_discord_voice_channel_activity,
        name="get_discord_activity",
    ),
    path("user-guilds/", get_user_guilds, name="discord-user-guilds"),
    path("discord-members/", get_discord_members, name="discord-members"),
    path("dtx_members", get_discord_members, name="dtx_members"),
    path(
        "organizations/<int:pk>/discord-members/",
        get_organization_discord_members,
        name="organization-discord-members",
    ),
    path("interactions/", discord_interactions, name="discord-interactions"),
    path("interactions", discord_interactions, name="discord-interactions-no-slash"),
    path(
        "search-discord-members/",
        search_discord_members,
        name="search-discord-members",
    ),
    path(
        "refresh-discord-members/",
        refresh_discord_members,
        name="refresh-discord-members",
    ),
    path(
        "organizations/<int:pk>/bot-status/",
        check_discord_bot_status,
        name="discord-bot-status",
    ),
    path(
        "organizations/<int:pk>/install-link/",
        discord_install_link,
        name="discord-install-link",
    ),
    path(
        "install/callback/",
        discord_install_callback,
        name="discord-install-callback",
    ),
    path(
        "organizations/<int:pk>/channels/",
        get_discord_channels,
        name="discord-channels",
    ),
    path(
        "organizations/<int:pk>/roles/",
        get_discord_roles,
        name="discord-roles",
    ),
]
