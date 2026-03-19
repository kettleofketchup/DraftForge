"""Discord role listing with Redis caching."""

import logging

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import Organization
from app.permissions_org import has_org_staff_access

log = logging.getLogger(__name__)

ROLES_CACHE_TTL = 600  # 10 minutes


def _fetch_guild_roles(guild_id):
    """Fetch roles from Discord API for a guild.

    Returns only roles the bot can mention (below bot's highest role,
    excluding @everyone and managed/bot roles).
    """
    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/roles"
    headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    roles = response.json()

    # Filter out @everyone (id == guild_id) and managed bot roles
    return [
        {
            "id": role["id"],
            "name": role["name"],
            "color": role["color"],
            "mentionable": role.get("mentionable", False),
            "position": role.get("position", 0),
        }
        for role in roles
        if role["id"] != guild_id  # Exclude @everyone
        and not role.get("managed", False)  # Exclude bot-managed roles
    ]


def _get_roles_cached(guild_id):
    """Get roles with Redis cache."""
    cache_key = f"discord_roles_{guild_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    roles = _fetch_guild_roles(guild_id)
    cache.set(cache_key, roles, timeout=ROLES_CACHE_TTL)
    return roles


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_discord_roles(request, pk):
    """List mentionable roles for an organization's Discord server.

    GET /api/discord/organizations/<pk>/roles/
    Query params:
        refresh=true -- bust cache and re-fetch from Discord
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

    if request.query_params.get("refresh") == "true":
        cache_key = f"discord_roles_{org.discord_server_id}"
        cache.delete(cache_key)

    try:
        roles = _get_roles_cached(org.discord_server_id)
    except Exception as e:
        log.error("Failed to fetch Discord roles for org %s: %s", org.pk, e)
        return Response({"error": "Failed to fetch Discord roles"}, status=502)

    return Response({"roles": roles})
