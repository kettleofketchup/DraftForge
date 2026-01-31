from django.urls import path

from .services.users import (
    get_discord_members,
    get_discord_voice_channel_activity,
    get_organization_discord_members,
    get_user_guilds,
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
]
