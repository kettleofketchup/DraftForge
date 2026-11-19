"""Discord channel listing with Redis caching."""

from typing import Any, Final

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import Organization
from app.permissions_org import has_org_staff_access
from telemetry.logging import get_logger

log = get_logger(__name__)

CHANNELS_CACHE_TTL = 600  # 10 minutes

# Forum channels require thread creation (different API) — include but flag them
CHANNEL_KINDS: Final[dict[str, dict[int, str]]] = {
    "text": {0: "text", 5: "announcement", 15: "forum"},
    "voice": {2: "voice", 13: "stage"},
}


def _fetch_guild_channels(guild_id: str, kind: str) -> list[dict[str, Any]]:
    """Fetch channels of one kind from Discord API for a guild."""
    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/channels"
    headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    labels = CHANNEL_KINDS[kind]
    return [
        {
            "id": ch["id"],
            "name": ch["name"],
            "type": ch["type"],
            "type_label": labels[ch["type"]],
        }
        for ch in response.json()
        if ch["type"] in labels
    ]


def _cache_key(guild_id: str, kind: str) -> str:
    if kind == "text":
        return f"discord_channels_{guild_id}"
    return f"discord_channels_{kind}_{guild_id}"


def _get_channels_cached(guild_id: str, kind: str) -> list[dict[str, Any]]:
    """Get channels with Redis cache."""
    cache_key = _cache_key(guild_id, kind)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    channels = _fetch_guild_channels(guild_id, kind)
    cache.set(cache_key, channels, timeout=CHANNELS_CACHE_TTL)
    return channels


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_discord_channels(request: Request, pk: int) -> Response:
    """List text or voice channels for an organization's Discord server.

    GET /api/discord/organizations/<pk>/channels/
    Query params:
        kind=text|voice — channel kind (default text)
        refresh=true — bust the cache for every kind and re-fetch from Discord
    """
    try:
        org = Organization.objects.get(pk=pk)
    except Organization.DoesNotExist:
        return Response({"error": "Organization not found"}, status=404)

    if not has_org_staff_access(request.user, org):
        return Response({"error": "Permission denied"}, status=403)

    kind = request.query_params.get("kind", "text")
    if kind not in CHANNEL_KINDS:
        return Response({"error": "Unknown channel kind"}, status=400)

    if not org.discord_server_id:
        return Response(
            {"error": "Organization has no Discord server configured"}, status=400
        )

    if request.query_params.get("refresh") == "true":
        cache.delete_many([_cache_key(org.discord_server_id, k) for k in CHANNEL_KINDS])
        log.info(
            "channels_cache_refreshed",
            system="discord",
            subsystem="channels",
            org_id=org.pk,
            kind=kind,
        )

    try:
        channels = _get_channels_cached(org.discord_server_id, kind)
    except Exception as e:
        log.error(
            "channels_fetch_failed",
            system="discord",
            subsystem="channels",
            org_id=org.pk,
            kind=kind,
            error=str(e),
        )
        return Response({"error": "Failed to fetch Discord channels"}, status=502)

    return Response({"channels": channels})
