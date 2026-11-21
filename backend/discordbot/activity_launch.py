"""Resolve notification launches into invites for the user's current voice channel.

Only Django calls this module. Gateway/Celery callers use the internal API so
Django remains the sole owner of bindings and draft permissions.
"""

from typing import Any, Literal, NamedTuple

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
from app.models import CustomUser
from app.permissions_org import can_edit_tournament
from discordbot.activity import discord_json
from discordbot.activity_intent import record_intent
from discordbot.activity_targets import draft_site_url, draft_tournament_id
from discordbot.models import DraftActivityChannel
from draft.models import Draft, HeroDraft
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


class BindResult(NamedTuple):
    outcome: Literal["bound", "replaced", "conflict", "channel_busy"]
    previous: HeroDraft | Draft | None


def _bind_channel(
    guild_id: str, channel_id: str, kind: str, draft: HeroDraft | Draft
) -> BindResult:
    """Upsert the binding unless it holds an unfinished draft of another (or no) tournament."""
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
        binding = (
            DraftActivityChannel.objects.select_for_update()
            .select_related("draft__game__tournament", "team_draft__tournament")
            .get(pk=binding.pk)
        )
        if binding.guild_id != guild_id:
            return BindResult("conflict", None)
        current = binding.draft or binding.team_draft
        if current is not None and _draft_label(current) == _draft_label(draft):
            return BindResult("bound", None)
        if current is not None and current.state not in FINISHED_STATES:
            current_tournament = draft_tournament_id(current)
            if current_tournament is None or current_tournament != draft_tournament_id(
                draft
            ):
                return BindResult("channel_busy", current)
        binding.draft = defaults["draft"]
        binding.team_draft = defaults["team_draft"]
        binding.save(update_fields=["draft", "team_draft"])
        return BindResult("replaced", current)


def _tournament_name(draft: HeroDraft | Draft) -> str | None:
    tournament = (
        draft.game.tournament if isinstance(draft, HeroDraft) else draft.tournament
    )
    return tournament.name if tournament else None


def prepare_activity_launch(
    discord_user_id: str, kind: str, draft_id: int
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "guild_id": None,
        "voice_channel_id": None,
        "previous_channel_draft": None,
        "intent_recorded": False,
        "tournament_id": None,
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
            details["tournament_id"] = draft_tournament_id(draft)
            participant = draft.draft_teams.filter(
                Q(tournament_team__captain=user) | Q(tournament_team__members=user)
            ).exists()
        else:
            draft = Draft.objects.select_related(
                "tournament__league__organization"
            ).get(pk=draft_id)
            tournament = draft.tournament
            details["tournament_id"] = draft_tournament_id(draft)
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
        bind = _bind_channel(guild_id, channel_id, kind, draft)
        if bind.previous is not None:
            details["previous_channel_draft"] = _draft_label(bind.previous)
        if bind.outcome == "channel_busy":
            busy = bind.previous
            details["busy_draft_id"] = busy.pk if busy else None
            details["busy_tournament_id"] = draft_tournament_id(busy) if busy else None
            other = (_tournament_name(busy) if busy else None) or "another event"
            return _failure(
                f"<#{channel_id}> is showing a live draft from {other}, another tournament. "
                f"Join a different voice channel and click Launch / Join Activity again, or open your draft in the browser: {draft_site_url(kind, draft)}"
            ), "channel_busy"
        if bind.outcome == "conflict":
            return _failure(
                "Your voice channel is already assigned to another draft. Join your team's draft channel or ask an organizer to update it."
            ), "conflict"
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
        intent_id = record_intent(
            discord_user_id,
            kind=kind,
            draft_id=draft.pk,
            tournament_id=details["tournament_id"],
            guild_id=guild_id,
            channel_id=channel_id,
        )
        details["intent_recorded"] = intent_id is not None
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
