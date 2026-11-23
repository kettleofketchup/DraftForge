import time

import requests
from cacheops import cached
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request

from app.models import CustomUser
from app.permissions import IsStaff

# Re-exported for existing importers; celery imports discord_members directly.
from discordbot.services.discord_members import (  # noqa: F401
    DISCORD_HTTP_TIMEOUT_S,
    DISCORD_MEMBER_CACHE_TTL_S,
    get_discord_members_data,
)
from discordbot.services.member_names import members_from_discord_payload
from org.activity import guild_sync_lock, release_guild_sync_lock
from org.discord_names import apply_guild_member_names, org_ids_for_guild
from org.models import Organization
from org.permissions import has_org_staff_access
from telemetry.logging import get_logger

log = get_logger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_guilds(request: Request) -> JsonResponse:
    access_token = request.user.social_auth.get(provider="discord").extra_data[
        "access_token"
    ]
    url = "https://discord.com/api/users/@me/guilds"
    headers = {"Authorization": f"Bearer {access_token}"}
    cache_key = "discord_guilds"
    cached_guilds = cache.get(cache_key)
    if cached_guilds:
        return JsonResponse({"guilds": cached_guilds}, safe=True)

    try:
        response = requests.get(url, headers=headers, timeout=DISCORD_HTTP_TIMEOUT_S)
        response.raise_for_status()
        guilds = response.json()
        cache.set(cache_key, guilds, timeout=5)
        return JsonResponse({"guilds": guilds}, safe=True)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)


def get_discord_members_api() -> JsonResponse:
    """
    API endpoint function that returns JsonResponse with discord members.
    """
    try:
        members = get_discord_members_data()
        return JsonResponse({"members": members}, safe=True)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
@cached(timeout=15)
def get_discord_members(request: Request) -> HttpResponse:
    return get_discord_members_api()


@api_view(["GET"])
@permission_classes([IsStaff])
def get_discord_voice_channel_activity(request: Request) -> JsonResponse:
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
    if not bot_token:
        return JsonResponse(
            {"error": "Discord bot token is not configured"}, status=503
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
        response_channels = requests.get(
            channels_url, headers=headers, timeout=DISCORD_HTTP_TIMEOUT_S
        )
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
        response_guild = requests.get(
            guild_url, headers=headers, timeout=DISCORD_HTTP_TIMEOUT_S
        )
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
        return JsonResponse(
            {"error": f"An unexpected error occurred: {str(e)}"}, status=500
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_organization_discord_members(request: Request, pk: int) -> JsonResponse:
    """
    Fetches Discord members for a specific organization's configured Discord server.

    Args:
        pk: Organization primary key

    Returns:
        JSON response with list of Discord members
    """
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
        log.error(
            "members_fetch_failed",
            system="discord",
            subsystem="users",
            org_id=pk,
            error=str(e),
        )
        return JsonResponse({"error": str(e)}, status=500)


DISCORD_MEMBERS_CACHE_TTL = 3600  # 1 hour


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_discord_members(request: Request) -> JsonResponse:
    """
    Search Discord members for a specific organization's Discord server.
    Results are cached in Redis for 1 hour.
    """
    query = request.query_params.get("q", "").strip().lower()
    org_id = request.query_params.get("org_id")

    if not org_id:
        return JsonResponse({"error": "org_id is required"}, status=400)

    if len(query) < 2:
        return JsonResponse(
            {"error": "Search query must be at least 2 characters"}, status=400
        )

    try:
        org = Organization.objects.get(pk=int(org_id))
    except (Organization.DoesNotExist, ValueError):
        return JsonResponse({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return JsonResponse(
            {"error": "You do not have access to this organization"}, status=403
        )

    if not org.discord_server_id:
        return JsonResponse(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    # Separate key from get_discord_members_data's own per-guild member cache
    cache_key = f"discord_members_search_{org.discord_server_id}"
    members = cache.get(cache_key)

    if members is None:
        try:
            members = get_discord_members_data(guild_id=org.discord_server_id)
        except Exception as e:
            log.error(
                "members_search_fetch_failed",
                system="discord",
                subsystem="users",
                org_id=org.pk,
                error=str(e),
            )
            return JsonResponse(
                {"error": "Failed to fetch Discord members"}, status=502
            )
        cache.set(cache_key, members, timeout=DISCORD_MEMBERS_CACHE_TTL)

    # Filter by query
    filtered = []
    for member in members:
        user = member.get("user", {})
        username = (user.get("username") or "").lower()
        global_name = (user.get("global_name") or "").lower()
        nick = (member.get("nick") or "").lower()

        if query in username or query in global_name or query in nick:
            filtered.append(member)

        if len(filtered) >= 20:
            break

    # Cross-reference with site accounts
    discord_ids = [m["user"]["id"] for m in filtered]
    linked_users = dict(
        CustomUser.objects.filter(discordId__in=discord_ids).values_list(
            "discordId", "pk"
        )
    )

    results = []
    for member in filtered:
        discord_id = member["user"]["id"]
        site_pk = linked_users.get(discord_id)
        results.append(
            {
                "user": member["user"],
                "nick": member.get("nick"),
                "has_site_account": site_pk is not None,
                "site_user_pk": site_pk,
            }
        )

    return JsonResponse({"results": results})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_discord_members(request: Request) -> JsonResponse:
    """Refresh Discord members cache for a specific organization."""
    org_id = request.data.get("org_id")

    if not org_id:
        return JsonResponse({"error": "org_id is required"}, status=400)

    try:
        org = Organization.objects.get(pk=int(org_id))
    except (Organization.DoesNotExist, ValueError):
        return JsonResponse({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return JsonResponse(
            {"error": "You do not have access to this organization"}, status=403
        )

    if not org.discord_server_id:
        return JsonResponse(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    # Rate limit: 5-minute cooldown per org
    cooldown_key = f"discord_refresh_cooldown_{org.discord_server_id}"
    if cache.get(cooldown_key):
        return JsonResponse(
            {"error": "Please wait before refreshing again"}, status=429
        )

    guild_id = org.discord_server_id
    cache_key = f"discord_members_search_{guild_id}"
    cache.delete(cache_key)

    fetched_at = time.time()
    locked = guild_sync_lock(guild_id)
    try:
        try:
            members = get_discord_members_data(guild_id=guild_id, force=True)
        except Exception as e:
            log.error(
                "members_refresh_failed",
                system="discord",
                subsystem="users",
                org_id=org.pk,
                error=str(e),
            )
            return JsonResponse(
                {"error": "Failed to fetch Discord members"}, status=502
            )
        cache.set(cache_key, members, timeout=DISCORD_MEMBERS_CACHE_TTL)
        cache.set(cooldown_key, True, timeout=300)  # 5-minute cooldown
        if locked:
            _apply_refreshed_names(guild_id, members, fetched_at, org.pk)
        else:
            log.info(
                "name_sync_skipped_guild_locked",
                system="discord",
                subsystem="name_sync",
                guild_id=guild_id,
                org_id=org.pk,
            )
    finally:
        if locked:
            release_guild_sync_lock(guild_id)

    return JsonResponse({"refreshed": True, "count": len(members)})


def _apply_refreshed_names(
    guild_id: str, raw_members: list[dict], fetched_at: float, org_id: int
) -> None:
    try:
        apply_guild_member_names(
            guild_id,
            org_ids_for_guild(guild_id),
            members_from_discord_payload(raw_members),
            complete=True,
            fetched_at=fetched_at,
        )
    except Exception:
        log.error(
            "name_sync_refresh_apply_failed",
            system="discord",
            subsystem="name_sync",
            guild_id=guild_id,
            org_id=org_id,
            exc_info=True,
        )


BOT_ACCESS_CACHE_TTL = 300  # 5 minutes


def bot_access_cache_key(guild_id: str) -> str:
    return f"discord_bot_access_{guild_id}"


def check_bot_guild_access(guild_id: str) -> bool:
    """
    Check if the bot can access a Discord guild by fetching 1 member.
    Returns True if the bot has access, False otherwise.
    Caches result for 5 minutes.
    """
    cache_key = bot_access_cache_key(guild_id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    bot_token = settings.DISCORD_BOT_TOKEN
    if not bot_token:
        return False

    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/members"
    headers = {"Authorization": f"Bot {bot_token}"}

    try:
        response = requests.get(url, headers=headers, params={"limit": 1}, timeout=5)
        has_access = response.status_code == 200
    except requests.exceptions.RequestException:
        has_access = False

    cache.set(cache_key, has_access, timeout=BOT_ACCESS_CACHE_TTL)
    return has_access
