import json
import logging

import requests
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from social_core.backends.oauth import BaseOAuth1, BaseOAuth2

# Create your views here.
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage
from social_django.utils import load_strategy, psa

from app.models import (
    CustomUser,
    Draft,
    DraftRound,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from app.permissions import IsStaff
from app.serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    PositionsSerializer,
    TeamSerializer,
    TournamentSerializer,
    UserSerializer,
)
from backend import settings

log = logging.getLogger(__name__)

from django.core.cache import cache


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_guilds(request):
    access_token = request.user.social_auth.get(provider="discord").extra_data[
        "access_token"
    ]
    url = "https://discord.com/api/users/@me/guilds"
    headers = {"Authorization": f"Bearer {access_token}"}
    cache_key = f"discord_guilds"
    cached_guilds = cache.get(cache_key)
    if cached_guilds:
        return JsonResponse({"guilds": cached_guilds}, safe=True)

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        guilds = response.json()
        cache.set(cache_key, guilds, timeout=5)
        return JsonResponse({"guilds": guilds}, safe=True)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)


def get_discord_members_data(guild_id=None):
    """
    Helper function to get discord members data as raw list (not JsonResponse).
    Useful for testing and internal operations.

    Args:
        guild_id: Discord guild ID. Defaults to settings.DISCORD_GUILD_ID if not provided.
    """
    if guild_id is None:
        guild_id = settings.DISCORD_GUILD_ID
    bot_token = settings.DISCORD_BOT_TOKEN  # Add your bot token in settings

    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/members"
    headers = {"Authorization": f"Bot {bot_token}"}
    after = None
    limit = 1000
    members = []
    cache_key = f"discord_members_{guild_id}"
    cached_members = cache.get(cache_key)

    if cached_members:
        return cached_members

    while True:
        params = {"limit": limit}
        if after:
            params["after"] = after

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            page = response.json()
            if not page:
                break
            after = page[-1]["user"]["id"]
            members.extend(page)
            if len(page) < limit:
                break
        except requests.exceptions.RequestException as e:
            raise Exception(f"Discord API error: {str(e)}")

    cache.set(cache_key, members, timeout=15)
    return members


def get_discord_members_api():
    """
    API endpoint function that returns JsonResponse with discord members.
    """
    try:
        members = get_discord_members_data()
        return JsonResponse({"members": members}, safe=True)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


from cacheops import cached, cached_view


@api_view(["GET"])
@permission_classes([AllowAny])
@cached(timeout=15)
def get_discord_members(request):
    return get_discord_members_api()


@api_view(["GET"])
@permission_classes([IsStaff])
def get_discord_voice_channel_activity(request):
    """
    Fetches all voice channels in the configured Discord guild that have active members.
    Returns a list of voice channels, each with its name, ID, and a list of member objects.
    """
    try:
        guild_id = settings.DISCORD_GUILD_ID
        bot_token = settings.DISCORD_BOT_TOKEN
        api_base_url = settings.DISCORD_API_BASE_URL
    except AttributeError as e:
        return JsonResponse(
            {"error": f"Discord API setting missing in Django settings: {e.name}"},
            status=500,
        )
    cache_key = f"voice_activity_{guild_id}"

    cached_voice_activity = cache.get(cache_key)
    if cached_voice_activity:
        return JsonResponse({"voice_activity": cached_voice_activity}, safe=True)

    headers = {"Authorization": f"Bot {bot_token}"}

    active_channels_data = []
    voice_channels_map = {}  # To store {channel_id: channel_name}

    try:
        # 1. Fetch all guild channels to identify voice channels and their names
        channels_url = f"{api_base_url}/guilds/{guild_id}/channels"
        response_channels = requests.get(channels_url, headers=headers)
        response_channels.raise_for_status()
        all_channels = response_channels.json()
        print(all_channels)
        for channel in all_channels:
            if channel.get("type") == 2:  # GUILD_VOICE type
                voice_channels_map[channel.get("id")] = channel.get(
                    "name", "Unknown Voice Channel"
                )

        # 2. Fetch guild resource, which includes the 'voice_states' array
        # The 'voice_states' array contains information about users in voice channels,
        # including their 'member' object.
        guild_url = f"{api_base_url}/guilds/{guild_id}"
        response_guild = requests.get(guild_url, headers=headers)
        response_guild.raise_for_status()
        guild_data = response_guild.json()
        print("Voice Channels Map:")
        print(voice_channels_map)
        # 3. Process voice_states to group members by channel
        # This temporary dictionary will hold {channel_id: [member_obj1, member_obj2]}
        members_in_channel_temp = {}
        print(f"guild_data: {guild_data.keys()}")

        for voice_state in guild_data.get("voice_states", []):
            channel_id = voice_state.get("channel_id")
            # The 'member' field in voice_state is a Guild Member object
            member_object = voice_state.get("member")
            print(member_object)
            # Ensure the user is in a voice channel we know and member data is present
            if channel_id and member_object and channel_id in voice_channels_map:
                if channel_id not in members_in_channel_temp:
                    members_in_channel_temp[channel_id] = []
                members_in_channel_temp[channel_id].append(member_object)
        print(f"members: {members_in_channel_temp}")
        # 4. Format the final output list
        for channel_id, members_list in members_in_channel_temp.items():
            # Only include channels that actually have members in them
            if members_list:
                active_channels_data.append(
                    {
                        "channel_id": channel_id,
                        "channel_name": voice_channels_map[channel_id],
                        "members": members_list,
                    }
                )
        cache.set(cache_key, active_channels_data, timeout=15)
        return JsonResponse({"active_voice_channels": active_channels_data}, safe=True)

    except requests.exceptions.RequestException as e:
        return JsonResponse(
            {"error": f"Error communicating with Discord API: {str(e)}"}, status=500
        )
    except Exception as e:

        # Catch any other unexpected errors during processing
        return JsonResponse(
            {"error": f"An unexpected error occurred: {str(e)}"}, status=500
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_organization_discord_members(request, pk):
    """
    Fetches Discord members for a specific organization's configured Discord server.

    Args:
        pk: Organization primary key

    Returns:
        JSON response with list of Discord members
    """
    from django.shortcuts import get_object_or_404

    from app.permissions_org import has_org_staff_access

    org = get_object_or_404(Organization, pk=pk)

    # Check user has staff access to this organization
    if not has_org_staff_access(request.user, org):
        return JsonResponse(
            {"error": "You do not have access to this organization"}, status=403
        )

    if not org.discord_server_id:
        return JsonResponse(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    try:
        members = get_discord_members_data(guild_id=org.discord_server_id)
        return JsonResponse({"members": members}, safe=True)
    except Exception as e:
        log.error(f"Error fetching Discord members for org {pk}: {e}")
        return JsonResponse({"error": str(e)}, status=500)
