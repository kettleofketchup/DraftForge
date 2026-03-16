from django.urls import path

from .services.channels import get_discord_channels
from .services.users import (
    check_discord_bot_status,
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
        "organizations/<int:pk>/channels/",
        get_discord_channels,
        name="discord-channels",
    ),
]
