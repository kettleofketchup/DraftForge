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
from discordbot.models import DraftActivityChannel, DraftActivityInstance
from telemetry.logging import get_logger

log = get_logger(__name__)

FINISHED_STATES = {"completed", "abandoned"}


class LaunchInput(serializers.Serializer):
    discord_user_id = serializers.RegexField(r"^[0-9]{1,20}$")
    kind = serializers.ChoiceField(choices=["hero", "team"])
    draft_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)


def _failure(content: str) -> dict[str, Any]:
    return {"success": False, "content": content, "components": []}


def _draft_label(draft: HeroDraft | Draft) -> str:
    return f"{'hero' if isinstance(draft, HeroDraft) else 'team'}:{draft.pk}"


def _pinned_to(draft: HeroDraft | Draft) -> dict[str, HeroDraft | Draft]:
    return {"draft": draft} if isinstance(draft, HeroDraft) else {"team_draft": draft}


def _instance_in_use(application_id: str, instance_id: str) -> bool:
    """Discord returns 404 once everyone has left an Activity instance."""
    try:
        data = discord_json(
            "GET",
            f"/applications/{application_id}/activity-instances/{instance_id}",
            bot=True,
            timeout=2,
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return False
        raise
    return bool(data.get("users"))


def _bind_channel(
    guild_id: str,
    channel_id: str,
    kind: str,
    draft: HeroDraft | Draft,
    application_id: str,
) -> tuple[str, str | None]:
    """Return (outcome, previous draft label); outcome is bound, rebound, conflict or in_use.

    A channel moves to the next draft only once its current draft has finished
    and nobody is still in the Activity running there; otherwise one click
    would drag every viewer in the channel into another match.
    """
    defaults = {
        "guild_id": guild_id,
        "draft": draft if kind == "hero" else None,
        "team_draft": draft if kind == "team" else None,
    }
    existing = (
        DraftActivityChannel.objects.select_related("draft", "team_draft")
        .filter(channel_id=channel_id, guild_id=guild_id)
        .first()
    )
    if existing is not None:
        current = existing.draft or existing.team_draft
        if (
            current is not None
            and _draft_label(current) != _draft_label(draft)
            and current.state in FINISHED_STATES
        ):
            running = DraftActivityInstance.objects.filter(
                guild_id=guild_id, channel_id=channel_id, **_pinned_to(current)
            ).values_list("instance_id", flat=True)
            if any(_instance_in_use(application_id, i) for i in running):
                return "in_use", _draft_label(current)
    with transaction.atomic():
        # Nested get_or_create handles a concurrent first binding through its
        # unique channel_id constraint. Lock the row before considering reuse.
        binding, _ = DraftActivityChannel.objects.get_or_create(
            channel_id=channel_id, defaults=defaults
        )
        binding = (
            DraftActivityChannel.objects.select_for_update()
            .select_related("draft", "team_draft")
            .get(pk=binding.pk)
        )
        if binding.guild_id != guild_id:
            return "conflict", None
        current = binding.draft or binding.team_draft
        if current is not None and _draft_label(current) == _draft_label(draft):
            return "bound", None
        if current is None or current.state not in FINISHED_STATES:
            return "conflict", None
        binding.draft = defaults["draft"]
        binding.team_draft = defaults["team_draft"]
        binding.save(update_fields=["draft", "team_draft"])
        # Instances that ended are moved too, so a later relaunch in this
        # channel resolves to the new draft rather than the finished one.
        DraftActivityInstance.objects.filter(
            guild_id=guild_id, channel_id=channel_id, **_pinned_to(current)
        ).update(draft=defaults["draft"], team_draft=defaults["team_draft"])
        return "rebound", _draft_label(current)


def prepare_activity_launch(
    discord_user_id: str, kind: str, draft_id: int
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "guild_id": None,
        "voice_channel_id": None,
        "rebound": False,
        "previous_draft": None,
    }
    result, outcome = _prepare_activity_launch(discord_user_id, kind, draft_id, details)
    log.info(
        "activity_launch_resolved",
        system="discord",
        subsystem="activity",
        discord_user_id=str(discord_user_id),
        kind=kind,
        draft_id=draft_id,
        outcome=outcome,
        **details,
    )
    return result


def _prepare_activity_launch(
    discord_user_id: str, kind: str, draft_id: int, details: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        return _failure(
            "Discord Activities are disabled. Open the draft in your browser."
        ), "disabled"
    try:
        # Bypass cacheops: a stale active-user entry must not reserve channels.
        user = CustomUser.objects.nocache().get(
            discordId=discord_user_id, is_active=True
        )
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
        ), "unlinked"
    except (HeroDraft.DoesNotExist, Draft.DoesNotExist):
        return _failure(
            "This draft is no longer available. Open its latest notification."
        ), "draft_missing"
    if not tournament or not (participant or can_edit_tournament(user, tournament)):
        return _failure(
            "You are not a participant or staff member of this draft."
        ), "not_participant"
    if draft.state in FINISHED_STATES:
        return _failure(
            "This draft has finished. Open it in your browser to view the results."
        ), "draft_finished"
    guild_id = str(
        tournament.league.organization.discord_server_id
        if tournament.league
        and tournament.league.organization
        and tournament.league.organization.discord_server_id
        else getattr(settings, "DISCORD_GUILD_ID", "")
    )
    details["guild_id"] = guild_id
    application_id = str(getattr(settings, "SOCIAL_AUTH_DISCORD_KEY", "") or "")
    if (
        not guild_id.isdigit()
        or not application_id.isdigit()
        or not settings.DISCORD_BOT_TOKEN
    ):
        return _failure(
            "Discord Activities are not configured for this server yet."
        ), "not_configured"
    try:
        voice = discord_json(
            "GET",
            f"/guilds/{guild_id}/voice-states/{discord_user_id}",
            bot=True,
            timeout=2,
        )
        channel_id = str(voice.get("channel_id") or "")
        if not channel_id.isdigit():
            return _failure(
                "Join your team's voice channel in this draft's server, then click Launch / Join Activity again."
            ), "no_voice"
        details["voice_channel_id"] = channel_id
        channel = discord_json("GET", f"/channels/{channel_id}", bot=True, timeout=2)
        if channel.get("type") != 2 or str(channel.get("guild_id")) != guild_id:
            return _failure(
                "Join a voice channel in this draft's server, then try again."
            ), "wrong_channel"
        bind, previous = _bind_channel(
            guild_id, channel_id, kind, draft, application_id
        )
        details["previous_draft"] = previous
        if bind == "in_use":
            return _failure(
                f"<#{channel_id}> is still running another draft's Activity. "
                "Move to your team's voice channel, then click Launch / Join Activity again."
            ), "in_use"
        if bind == "conflict":
            return _failure(
                "Your voice channel is already assigned to another draft. Join your team's draft channel or ask an organizer to update it."
            ), "conflict"
        details["rebound"] = bind == "rebound"
        invite = discord_json(
            "POST",
            f"/channels/{channel_id}/invites",
            bot=True,
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
            ), "no_voice"
        return _failure(
            "Discord could not prepare the Activity. The bot needs Connect and Create Invite permissions in your voice channel."
        ), "discord_error"
    except (requests.RequestException, KeyError, TypeError, ValueError, IntegrityError):
        return _failure(
            "Could not prepare the Activity. Please try again shortly."
        ), "error"
    return {
        "success": True,
        "content": (
            f"This invite opens DraftForge in <#{channel_id}>. Discord launches it "
            "there or joins the Activity already running. It expires in five minutes. "
            f"If you're no longer in <#{channel_id}>, click Launch / Join Activity "
            "again from your current voice channel."
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
    }, "invite_created"


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def activity_launch(request: Request) -> Response:
    payload = LaunchInput(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(prepare_activity_launch(**payload.validated_data))
