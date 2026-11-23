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
from app.models import CustomUser, Tournament
from discordbot.activity import discord_json
from discordbot.activity_intent import record_intent
from discordbot.activity_targets import draft_site_url, draft_tournament_id
from discordbot.models import DraftActivityChannel
from draft.models import Draft, HeroDraft
from events.models import Event
from telemetry.logging import get_logger
from tournament.permissions import can_edit_tournament

log = get_logger(__name__)

FINISHED_STATES = {"completed", "abandoned"}
NOTIFICATION_INVITE_MAX_AGE = 24 * 60 * 60


class DraftRefInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["hero", "team"])
    draft_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)


class LaunchInput(DraftRefInput):
    discord_user_id = serializers.RegexField(r"^[0-9]{1,20}$")


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


def _guild_id(tournament: Tournament) -> str:
    org = tournament.league.organization if tournament.league else None
    if org and org.discord_server_id:
        return str(org.discord_server_id)
    return str(getattr(settings, "DISCORD_GUILD_ID", ""))


def _application_id() -> str:
    return str(getattr(settings, "SOCIAL_AUTH_DISCORD_KEY", "") or "")


def _activity_configured(guild_id: str, application_id: str) -> bool:
    return (
        guild_id.isdigit()
        and application_id.isdigit()
        and bool(settings.DISCORD_BOT_TOKEN)
    )


def _invite_code(invite: dict[str, Any]) -> str:
    code = invite["code"]
    if (
        not isinstance(code, str)
        or not code
        or not all(c.isascii() and (c.isalnum() or c in "-_") for c in code)
    ):
        raise ValueError("Invalid Discord invite")
    return code


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
    guild_id = _guild_id(tournament)
    details["guild_id"] = guild_id
    application_id = _application_id()
    if not _activity_configured(guild_id, application_id):
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
        code = _invite_code(invite)
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


def _notification_channel(
    kind: str, draft: HeroDraft | Draft, tournament: Tournament, guild_id: str
) -> tuple[str | None, str]:
    """The one voice channel every recipient can share, or None and why not."""
    bound = list(
        DraftActivityChannel.objects.nocache()
        .filter(
            guild_id=guild_id, **{"draft" if kind == "hero" else "team_draft": draft}
        )
        .values_list("channel_id", flat=True)[:2]
    )
    if len(bound) == 1:
        return bound[0], "bound_channel"
    if bound:
        return None, "several_bound_channels"
    # Concurrent hero drafts of one tournament would fight over the event channel.
    if kind == "hero":
        return None, "no_bound_channel"
    channel_id = (
        Event.objects.nocache()
        .filter(tournament=tournament)
        .exclude(event_voice_channel_id="")
        .values_list("event_voice_channel_id", flat=True)
        .first()
    )
    if not channel_id:
        return None, "no_event_channel"
    return channel_id, "event_channel"


def prepare_notification_invite(kind: str, draft_id: int) -> dict[str, Any]:
    details: dict[str, Any] = {"guild_id": None, "channel_id": None, "source": None}
    url, outcome = _prepare_notification_invite(kind, draft_id, details)
    log.info(
        "activity_notification_invite_resolved",
        system="discord",
        subsystem="activity",
        kind=kind,
        draft_id=draft_id,
        outcome=outcome,
        **details,
    )
    return {"url": url, "channel_id": details["channel_id"] if url else None}


def _prepare_notification_invite(
    kind: str, draft_id: int, details: dict[str, Any]
) -> tuple[str | None, str]:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        return None, "disabled"
    try:
        if kind == "hero":
            draft: HeroDraft | Draft = HeroDraft.objects.select_related(
                "game__tournament__league__organization"
            ).get(pk=draft_id)
            tournament = draft.game.tournament
        else:
            draft = Draft.objects.select_related(
                "tournament__league__organization"
            ).get(pk=draft_id)
            tournament = draft.tournament
    except (HeroDraft.DoesNotExist, Draft.DoesNotExist):
        return None, "draft_missing"
    if tournament is None:
        return None, "no_tournament"
    if draft.state in FINISHED_STATES:
        return None, "draft_finished"
    guild_id = _guild_id(tournament)
    details["guild_id"] = guild_id
    application_id = _application_id()
    if not _activity_configured(guild_id, application_id):
        return None, "not_configured"
    channel_id, source = _notification_channel(kind, draft, tournament, guild_id)
    details["source"] = source
    if channel_id is None:
        return None, source
    details["channel_id"] = channel_id
    try:
        channel = discord_json("GET", f"/channels/{channel_id}", bot=True, timeout=2)
        if channel.get("type") != 2 or str(channel.get("guild_id")) != guild_id:
            return None, "wrong_channel"
        bind = _bind_channel(guild_id, channel_id, kind, draft)
        if bind.outcome in ("conflict", "channel_busy"):
            return None, bind.outcome
        invite = discord_json(
            "POST",
            f"/channels/{channel_id}/invites",
            bot=True,
            timeout=2,
            json={
                "target_type": 2,
                "target_application_id": application_id,
                "max_age": NOTIFICATION_INVITE_MAX_AGE,
                "max_uses": 0,
                "unique": False,
            },
        )
        code = _invite_code(invite)
    except requests.HTTPError:
        return None, "discord_error"
    except (requests.RequestException, KeyError, TypeError, ValueError, IntegrityError):
        return None, "error"
    return f"https://discord.gg/{code}", "invite_created"


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def activity_notification_invite(request: Request) -> Response:
    payload = DraftRefInput(data=request.data)
    payload.is_valid(raise_exception=True)
    return Response(prepare_notification_invite(**payload.validated_data))
