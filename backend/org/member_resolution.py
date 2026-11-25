"""Resolve a user and their cached Discord guild member for member-add endpoints."""

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from app.models import CustomUser
from discordbot.services.member_names import normalise_name
from org.models import Organization
from user.models import PositionsModel


def find_member(members: list[dict], discord_id: str) -> dict | None:
    for m in members:
        if m.get("user", {}).get("id") == discord_id:
            return m
    return None


def cached_guild_member(
    org: Organization | None, discord_id: str | None
) -> dict | None:
    if not org or not org.discord_server_id or not discord_id:
        return None
    members = cache.get(f"discord_members_search_{org.discord_server_id}") or []
    return find_member(members, discord_id)


def member_nick(member: dict | None) -> str | None:
    if member is None:
        return None
    return normalise_name(member.get("nick"))


def resolve_member_user(
    data: dict, org: Organization | None = None
) -> tuple[CustomUser, dict | None] | Response:
    """
    Resolve a user from user_id or discord_id, plus their cached guild member.

    Discord member data comes from the backend's own cache, never the client.
    No Discord fetch is made; a cold cache yields ``None`` for the member.
    """
    user_id = data.get("user_id")
    discord_id = data.get("discord_id")

    if user_id:
        try:
            user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        return user, cached_guild_member(org, user.discordId)
    elif discord_id:
        existing = CustomUser.objects.filter(discordId=discord_id).first()
        if existing:
            return existing, cached_guild_member(org, discord_id)

        if not org or not org.discord_server_id:
            return Response(
                {"error": "Cannot resolve Discord user without org Discord server"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        members = cache.get(f"discord_members_search_{org.discord_server_id}")
        if not members:
            return Response(
                {
                    "error": "Discord member cache is empty. "
                    "Please refresh Discord members first."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        discord_member = find_member(members, discord_id)
        if not discord_member:
            return Response(
                {"error": "Discord member not found in cache"},
                status=status.HTTP_404_NOT_FOUND,
            )

        positions = PositionsModel.objects.create()
        user = CustomUser(positions=positions)
        user.createFromDiscordData(discord_member)
        user.save()
        return user, discord_member
    else:
        return Response(
            {"error": "user_id or discord_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
