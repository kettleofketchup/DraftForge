"""
Test-only endpoint for seeding the Discord members cache.

Populates the Redis cache key used by search_discord_members so that
Playwright tests can exercise the Discord tab in AddUserModal without
a real Discord API connection.
"""

import logging

from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.utils import isTestEnvironment
from tests.data.users import TOURNAMENT_USERS

log = logging.getLogger(__name__)


def _make_discord_member(discord_id: str, username: str, nick: str | None = None):
    """Build a minimal Discord guild-member dict matching the Discord API shape."""
    return {
        "user": {
            "id": discord_id,
            "username": username,
            "global_name": nick or username,
            "avatar": None,
            "discriminator": "0",
            "public_flags": 0,
        },
        "nick": nick,
    }


# Unlinked Discord members (no matching CustomUser in the DB).
# Tests can use these to exercise "add from Discord ID" flow.
UNLINKED_DISCORD_MEMBERS = [
    _make_discord_member(
        "900000000000000001", "unlinked_discord_user", "Unlinked Test"
    ),
    _make_discord_member("900000000000000002", "unlinked_discord_alt", "Unlinked Alt"),
]


def _build_test_discord_members():
    """Build the full list of fake Discord members for the test cache."""
    members = []

    # Tournament users — these have matching CustomUser.discordId in the DB,
    # so search_discord_members will flag them has_site_account=True.
    for username, user in TOURNAMENT_USERS.items():
        if user.discord_id:
            members.append(
                _make_discord_member(user.discord_id, username, user.nickname)
            )

    # Unlinked members — no CustomUser match
    members.extend(UNLINKED_DISCORD_MEMBERS)

    return members


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def seed_discord_members(request, org_id: int):
    """
    TEST ONLY: Seed the Discord members Redis cache for an organization.

    This populates the same cache key that search_discord_members reads,
    so Playwright tests can search and add Discord members without a real
    Discord bot connection.

    POST /api/tests/discord/<org_id>/seed-members/
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Organization

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": f"Organization with pk {org_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not org.discord_server_id:
        return Response(
            {"error": "Organization has no discord_server_id configured"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    members = _build_test_discord_members()
    cache_key = f"discord_members_search_{org.discord_server_id}"
    cache.set(cache_key, members, timeout=3600)

    log.info(f"Seeded {len(members)} Discord members into cache key {cache_key}")

    return Response(
        {
            "seeded": True,
            "count": len(members),
            "cache_key": cache_key,
        }
    )
