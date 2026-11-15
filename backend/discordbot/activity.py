"""Discord Activity identity verification and narrowly scoped draft credentials."""

from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from app.serializers import UserSerializer
from discordbot.activity_auth import issue_activity_token
from discordbot.models import DraftActivityChannel, DraftActivityInstance


class ActivityInput(serializers.Serializer):
    code = serializers.CharField(max_length=2048)
    instance_id = serializers.RegexField(r"^[A-Za-z0-9_-]+$", max_length=100)


def discord_json(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("timeout", 10)
    response = requests.request(method, f"https://discord.com/api/v10{path}", **kwargs)
    response.raise_for_status()
    return response.json()


def resolve_instance(instance_id: str, discord_user_id: str) -> DraftActivityInstance:
    """Trust Discord's instance metadata, never channel IDs supplied by the iframe."""
    instance = discord_json(
        "GET",
        f"/applications/{settings.SOCIAL_AUTH_DISCORD_KEY}/activity-instances/{instance_id}",
        headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
    )
    if str(discord_user_id) not in {str(p) for p in instance["users"]}:
        raise AuthenticationFailed("You are not a participant in this Activity.")
    location = instance["location"]
    if location.get("kind") != "gc":
        raise AuthenticationFailed("Join a configured server voice channel.")
    guild_id, channel_id = str(location["guild_id"]), str(location["channel_id"])
    with transaction.atomic():
        existing = DraftActivityInstance.objects.filter(instance_id=instance_id).first()
        if existing:
            if (existing.guild_id, existing.channel_id) != (guild_id, channel_id):
                raise AuthenticationFailed("Activity location changed.")
            return existing
        binding = DraftActivityChannel.objects.filter(
            guild_id=guild_id, channel_id=channel_id
        ).first()
        if not binding:
            raise AuthenticationFailed("This voice channel has no draft configured.")
        instance, _ = DraftActivityInstance.objects.get_or_create(
            instance_id=instance_id,
            defaults={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "draft": binding.draft,
                "team_draft": binding.team_draft,
            },
        )
        return instance


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def activity_session(request: Request) -> Response:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        return Response({"error": "Discord Activities are disabled."}, status=404)
    payload = ActivityInput(data=request.data)
    payload.is_valid(raise_exception=True)
    try:
        oauth = discord_json(
            "POST",
            "/oauth2/token",
            data={
                "client_id": settings.SOCIAL_AUTH_DISCORD_KEY,
                "client_secret": settings.SOCIAL_AUTH_DISCORD_SECRET,
                "grant_type": "authorization_code",
                "code": payload.validated_data["code"],
            },
        )
        identity = discord_json(
            "GET",
            "/users/@me",
            headers={"Authorization": f"Bearer {oauth['access_token']}"},
        )
        user = CustomUser.objects.get(discordId=identity["id"], is_active=True)
        instance = resolve_instance(
            payload.validated_data["instance_id"], identity["id"]
        )
    except CustomUser.DoesNotExist:
        raise AuthenticationFailed(
            "Link your Discord account on the DraftForge website first."
        )
    except (requests.RequestException, KeyError, TypeError, ValueError):
        # Never return OAuth credentials or upstream response bodies in errors.
        raise AuthenticationFailed("Could not verify the Discord Activity.")
    token = issue_activity_token(user, instance)
    return Response(
        {
            "token": token,
            "draft_id": instance.draft_id or instance.team_draft_id,
            "kind": "hero" if instance.draft_id else "team",
            "tournament_id": instance.team_draft.tournament_id
            if instance.team_draft_id
            else None,
            "user": UserSerializer(user).data,
            "access_token": oauth["access_token"],
        },
        headers={"Cache-Control": "no-store"},
    )


def launch_message() -> dict[str, Any]:
    """Components V2 payload, deliberately not an external link button."""
    return {
        "flags": 32768,
        "components": [
            {
                "type": 10,
                "content": "Join your team's voice channel, then launch the draft.",
            },
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 1,
                        "label": "Launch Draft",
                        "custom_id": "draft_activity:launch",
                    }
                ],
            },
        ],
    }
