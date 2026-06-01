"""Discord channel listing with Redis caching."""

from telemetry.logging import get_logger

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import Organization
from app.permissions_org import has_org_staff_access

log = get_logger(__name__)

CHANNELS_CACHE_TTL = 600  # 10 minutes


def _fetch_guild_channels(guild_id):
    """Fetch text channels from Discord API for a guild."""
    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/channels"
    headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    # Type 0 = text, Type 5 = announcement, Type 15 = forum
    # Forum channels require thread creation (different API) — include but flag them
    POSTABLE_TYPES = {0, 5, 15}
    TYPE_LABELS = {0: "text", 5: "announcement", 15: "forum"}
    return [
        {
            "id": ch["id"],
            "name": ch["name"],
            "type": ch["type"],
            "type_label": TYPE_LABELS.get(ch["type"], "unknown"),
        }
        for ch in response.json()
        if ch["type"] in POSTABLE_TYPES
    ]


def _get_channels_cached(guild_id):
    """Get channels with Redis cache."""
    cache_key = f"discord_channels_{guild_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    channels = _fetch_guild_channels(guild_id)
    cache.set(cache_key, channels, timeout=CHANNELS_CACHE_TTL)
    return channels


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_discord_channels(request, pk):
    """List text channels for an organization's Discord server.

    GET /api/discord/organizations/<pk>/channels/
    Query params:
        refresh=true — bust cache and re-fetch from Discord
    """
    try:
        org = Organization.objects.get(pk=pk)
    except Organization.DoesNotExist:
        return Response({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return Response({"error": "Permission denied"}, status=403)

    if not org.discord_server_id:
        return Response(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    # Force refresh if requested
    if request.query_params.get("refresh") == "true":
        cache_key = f"discord_channels_{org.discord_server_id}"
        cache.delete(cache_key)

    try:
        channels = _get_channels_cached(org.discord_server_id)
    except Exception as e:
        log.error("Failed to fetch Discord channels for org %s: %s", org.pk, e)
        return Response({"error": "Failed to fetch Discord channels"}, status=502)

    return Response({"channels": channels})
