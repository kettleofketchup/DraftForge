"""Discord Activity identity verification and narrowly scoped draft credentials."""

from typing import Any, Literal

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
from discordbot import activity_fake
from discordbot.activity_auth import (
    ActivityIdentity,
    instance_pin,
    issue_activity_token,
    session_tournament,
)
from discordbot.activity_intent import LaunchIntent, peek_intent
from discordbot.activity_menu import resolve_initial_view
from discordbot.activity_roles import draft_role
from discordbot.activity_targets import draft_tournament_id
from discordbot.models import DraftActivityChannel, DraftActivityInstance
from discordbot.utils import DISCORD_API_BASE, _get_headers, _rate_limited_request
from draft.models import Draft, HeroDraft
from telemetry.logging import get_logger

log = get_logger(__name__)

SessionMode = Literal["first", "refresh", "legacy"]


class CurrentViewInput(serializers.Serializer):
    kind = serializers.ChoiceField(["team", "hero", "bracket"])
    id = serializers.IntegerField(min_value=1, required=False)


class ActivityInput(serializers.Serializer):
    code = serializers.CharField(max_length=2048)
    instance_id = serializers.RegexField(r"^[A-Za-z0-9_-]+$", max_length=100)
    mode = serializers.ChoiceField(["first", "refresh"], required=False)
    current_view = CurrentViewInput(required=False)
    scope = serializers.ChoiceField(["draft", "tournament"], required=False)


def discord_json(
    method: str, path: str, *, bot: bool = False, **kwargs: Any
) -> dict[str, Any]:
    """Bot calls share the bot-wide rate limiter; OAuth calls carry their own token."""
    if activity_fake.active():
        fake = activity_fake.answer(method, path, kwargs)
        if fake is not None:
            return fake
    kwargs.setdefault("timeout", 10)
    url = f"{DISCORD_API_BASE}{path}"
    if bot:
        kwargs["headers"] = {**_get_headers(), **kwargs.get("headers", {})}
        try:
            response = _rate_limited_request(method, url, **kwargs)
        except RuntimeError as exc:
            raise requests.ConnectionError("Discord rate limit") from exc
    else:
        response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response.json()


def _intent_draft(intent: LaunchIntent) -> HeroDraft | Draft | None:
    if intent.kind == "hero":
        return (
            HeroDraft.objects.nocache()
            .select_related("game")
            .filter(pk=intent.draft_id)
            .first()
        )
    return Draft.objects.nocache().filter(pk=intent.draft_id).first()


def _seed_draft(
    binding: DraftActivityChannel | None, intent: LaunchIntent | None
) -> HeroDraft | Draft | None:
    channel_draft = None if binding is None else binding.draft or binding.team_draft
    target = None if intent is None else _intent_draft(intent)
    if target is not None and (
        channel_draft is None
        or draft_tournament_id(target) == draft_tournament_id(channel_draft)
    ):
        return target
    return channel_draft


def resolve_instance(
    instance_id: str, discord_user_id: str
) -> tuple[DraftActivityInstance, bool]:
    """Trust Discord's instance metadata, never channel IDs supplied by the iframe."""
    instance = discord_json(
        "GET",
        f"/applications/{activity_fake.client_id()}/activity-instances/{instance_id}",
        bot=True,
    )
    if str(discord_user_id) not in {str(p) for p in instance["users"]}:
        raise AuthenticationFailed("You are not a participant in this Activity.")
    location = instance["location"]
    if location.get("kind") != "gc":
        raise AuthenticationFailed("Join a configured server voice channel.")
    guild_id, channel_id = str(location["guild_id"]), str(location["channel_id"])
    existing = (
        DraftActivityInstance.objects.nocache().filter(instance_id=instance_id).first()
    )
    if existing:
        if (existing.guild_id, existing.channel_id) != (guild_id, channel_id):
            raise AuthenticationFailed("Activity location changed.")
        return existing, False
    intent = peek_intent(str(discord_user_id))
    if intent is not None and not intent.applies_to(guild_id, channel_id):
        intent = None
    with transaction.atomic():
        binding = (
            DraftActivityChannel.objects.nocache()
            .select_related("draft__game", "team_draft")
            .filter(guild_id=guild_id, channel_id=channel_id)
            .first()
        )
        seed = _seed_draft(binding, intent)
        if seed is None:
            raise AuthenticationFailed("This voice channel has no draft configured.")
        is_hero = isinstance(seed, HeroDraft)
        return DraftActivityInstance.objects.get_or_create(
            instance_id=instance_id,
            defaults={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "draft": seed if is_hero else None,
                "team_draft": None if is_hero else seed,
            },
        )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def activity_session(request: Request) -> Response:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        return Response({"error": "Discord Activities are disabled."}, status=404)
    payload = ActivityInput(data=request.data)
    payload.is_valid(raise_exception=True)
    mode: SessionMode = payload.validated_data.get("mode", "legacy")
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
        discord_user_id = str(identity["id"])
        user = CustomUser.objects.nocache().get(
            discordId=discord_user_id, is_active=True
        )
        instance, created = resolve_instance(
            payload.validated_data["instance_id"], discord_user_id
        )
    except CustomUser.DoesNotExist:
        raise AuthenticationFailed(
            "Link your Discord account on the DraftForge website first."
        )
    except (requests.RequestException, KeyError, TypeError, ValueError):
        # Never return OAuth credentials or upstream response bodies in errors.
        raise AuthenticationFailed("Could not verify the Discord Activity.")
    # A refresh never widens a draft-scope frame to whatever the channel holds now.
    channel_fallback = not (
        mode == "refresh" and payload.validated_data.get("scope") == "draft"
    )
    tournament_id = session_tournament(instance, channel_fallback=channel_fallback)
    scope = "draft" if tournament_id is None else "tournament"
    token = issue_activity_token(user, instance, channel_fallback=channel_fallback)
    pin = instance_pin(instance)
    common = {
        "system": "discord",
        "subsystem": "activity",
        "user_id": user.pk,
        "discord_user_id": discord_user_id,
        "instance_id": instance.instance_id,
        "guild_id": instance.guild_id,
        "channel_id": instance.channel_id,
        "tournament_id": tournament_id,
    }
    initial_view: dict[str, object] | None = None
    launch_intent: dict[str, object] | None = None
    notice: dict[str, object] | None = None
    if mode == "refresh":
        current = payload.validated_data.get("current_view") or {}
        log.info(
            "activity_session_refreshed",
            **common,
            current_kind=current.get("kind"),
            current_id=current.get("id"),
        )
    elif mode == "legacy":
        # 0.14.x bundles render only the instance's first draft.
        log.info(
            "activity_session_started",
            **common,
            mode=mode,
            instance_created=created,
            scope=scope,
            initial_kind=pin["kind"],
            initial_draft_id=pin["draft"],
            source="legacy",
            role=draft_role(user, pin["kind"], pin["draft"]),
            notice=False,
            intent_id=None,
        )
    else:
        identity = ActivityIdentity(
            user=user,
            instance=instance,
            tournament_id=tournament_id,
            pin=None if tournament_id is not None else pin,
        )
        resolved = resolve_initial_view(identity, discord_user_id)
        initial_view = resolved.view
        launch_intent = resolved.launch_intent
        notice = resolved.notice
        initial_kind = None if initial_view is None else initial_view["kind"]
        initial_id = None if initial_view is None else initial_view.get("id")
        intent_ref = launch_intent or notice or {}
        log.info(
            "activity_session_started",
            **common,
            mode=mode,
            instance_created=created,
            scope=scope,
            initial_kind=initial_kind,
            initial_draft_id=initial_id,
            source=resolved.source,
            role=(
                draft_role(user, initial_kind, initial_id)
                if initial_kind in ("hero", "team") and isinstance(initial_id, int)
                else None
            ),
            notice=notice is not None,
            intent_id=intent_ref.get("intent_id"),
        )
    return Response(
        {
            "token": token,
            "scope": scope,
            "tournament_id": tournament_id,
            "initial_view": initial_view,
            "launch_intent": launch_intent,
            "draft_id": pin["draft"],
            "kind": pin["kind"],
            "site_url": settings.SITE_URL,
            "notice": notice,
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
