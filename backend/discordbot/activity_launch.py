"""Resolve notification launches into invites for the user's current voice channel.

Only Django calls this module. Gateway/Celery callers use the internal API so
Django remains the sole owner of bindings and draft permissions.
"""

from typing import Any

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.models import CustomUser, Draft, HeroDraft
from app.permissions_org import can_edit_tournament
from discordbot.activity import discord_json
from discordbot.models import DraftActivityChannel


class LaunchInput(serializers.Serializer):
    discord_user_id = serializers.RegexField(r"^[0-9]{1,20}$")
    kind = serializers.ChoiceField(choices=["hero", "team"])
    draft_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)


def _failure(content: str) -> dict[str, Any]:
    return {"success": False, "content": content, "components": []}


def _bind_channel(
    guild_id: str, channel_id: str, kind: str, draft: HeroDraft | Draft
) -> bool:
    """Never replace another draft because somebody clicked a stale DM."""
    defaults = {
        "guild_id": guild_id,
        "draft": draft if kind == "hero" else None,
        "team_draft": draft if kind == "team" else None,
    }
    with transaction.atomic():
        # Nested get_or_create handles a concurrent first binding through its
        # unique channel_id constraint. Lock the row before considering reuse.
        binding, _ = DraftActivityChannel.objects.get_or_create(
            channel_id=channel_id, defaults=defaults
        )
        binding = DraftActivityChannel.objects.select_for_update().get(pk=binding.pk)
        same = (
            binding.draft_id == draft.pk
            if kind == "hero"
            else binding.team_draft_id == draft.pk
        )
        if binding.guild_id != guild_id:
            return False
        if same:
            return True
        # A completed draft can still have a live Discord instance pinned to
        # it. Only an operator who has stopped that instance may reconfigure
        # the channel; a notification must never silently redirect a channel.
        return False


def prepare_activity_launch(
    discord_user_id: str, kind: str, draft_id: int
) -> dict[str, Any]:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        return _failure(
            "Discord Activities are disabled. Open the draft in your browser."
        )
    try:
        user = CustomUser.objects.get(discordId=discord_user_id, is_active=True)
        if kind == "hero":
            draft = HeroDraft.objects.select_related(
                "game__tournament__league__organization"
            ).get(pk=draft_id)
            tournament = draft.game.tournament
            participant = draft.draft_teams.filter(
                Q(tournament_team__captain=user) | Q(tournament_team__members=user)
            ).exists()
        else:
            draft = Draft.objects.select_related(
                "tournament__league__organization"
            ).get(pk=draft_id)
            tournament = draft.tournament
            participant = bool(
                tournament
                and (
                    tournament.users.filter(pk=user.pk).exists()
                    or tournament.teams.filter(
                        Q(captain=user) | Q(members=user)
                    ).exists()
                )
            )
    except CustomUser.DoesNotExist:
        return _failure(
            "Link your Discord account on DraftForge before launching an Activity."
        )
    except (HeroDraft.DoesNotExist, Draft.DoesNotExist):
        return _failure(
            "This draft is no longer available. Open its latest notification."
        )
    if not tournament or not (participant or can_edit_tournament(user, tournament)):
        return _failure("You are not a participant or staff member of this draft.")
    if draft.state in {"completed", "abandoned"}:
        return _failure(
            "This draft has finished. Open it in your browser to view the results."
        )
    guild_id = str(
        tournament.league.organization.discord_server_id
        if tournament.league
        and tournament.league.organization
        and tournament.league.organization.discord_server_id
        else getattr(settings, "DISCORD_GUILD_ID", "")
    )
    application_id = str(getattr(settings, "SOCIAL_AUTH_DISCORD_KEY", "") or "")
    if (
        not guild_id.isdigit()
        or not application_id.isdigit()
        or not settings.DISCORD_BOT_TOKEN
    ):
        return _failure("Discord Activities are not configured for this server yet.")
    headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
    try:
        voice = discord_json(
            "GET",
            f"/guilds/{guild_id}/voice-states/{discord_user_id}",
            headers=headers,
            timeout=2,
        )
        channel_id = str(voice.get("channel_id") or "")
        if not channel_id.isdigit():
            return _failure(
                "Join your team's voice channel in this draft's server, then click Launch / Join Activity again."
            )
        channel = discord_json(
            "GET", f"/channels/{channel_id}", headers=headers, timeout=2
        )
        if channel.get("type") != 2 or str(channel.get("guild_id")) != guild_id:
            return _failure(
                "Join a voice channel in this draft's server, then try again."
            )
        # Recheck immediately before binding/invite creation; cached gateway
        # voice state is never sufficient to choose another channel for a user.
        current = discord_json(
            "GET",
            f"/guilds/{guild_id}/voice-states/{discord_user_id}",
            headers=headers,
            timeout=2,
        )
        if str(current.get("channel_id") or "") != channel_id:
            return _failure(
                "Your voice channel changed. Click Launch / Join Activity again."
            )
        if not _bind_channel(guild_id, channel_id, kind, draft):
            return _failure(
                "Your voice channel is already assigned to another draft. Join your team's draft channel or ask an organizer to update it."
            )
        invite = discord_json(
            "POST",
            f"/channels/{channel_id}/invites",
            headers=headers,
            timeout=2,
            json={
                "target_type": 2,
                "target_application_id": application_id,
                "max_age": 300,
                "max_uses": 1,
                "unique": True,
            },
        )
        code = invite["code"]
        if (
            not isinstance(code, str)
            or not code
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in code)
        ):
            raise ValueError("Invalid Discord invite")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return _failure(
                "Join your team's voice channel in this draft's server, then click Launch / Join Activity again."
            )
        return _failure(
            "Discord could not prepare the Activity. The bot needs Connect and Create Invite permissions in your voice channel."
        )
    except (requests.RequestException, KeyError, TypeError, ValueError, IntegrityError):
        return _failure("Could not prepare the Activity. Please try again shortly.")
    return {
        "success": True,
        "content": (
            f"Open the Activity in <#{channel_id}>. Discord will launch it or join "
            "the existing Activity. This invite expires in five minutes. "
            "If you move channels, click the original notification again."
        ),
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 5,
                        "label": "Launch / Join Activity",
                        "url": f"https://discord.gg/{code}",
                    }
                ],
            }
        ],
    }


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def activity_launch(request: Request) -> Response:
    payload = LaunchInput(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(prepare_activity_launch(**payload.validated_data))
