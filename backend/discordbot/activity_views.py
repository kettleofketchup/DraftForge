"""Activity switcher endpoints authenticated by the Activity credential."""

from typing import Any

from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from discordbot.activity_auth import (
    MAX_DATABASE_ID,
    OUT_OF_SCOPE,
    ActivityAuthentication,
    ActivityIdentity,
    scope_allows,
)
from discordbot.activity_intent import consume_intent
from discordbot.activity_menu import external_path, list_drafts
from discordbot.activity_roles import Role, draft_role
from telemetry.logging import get_logger

log = get_logger(__name__)

TRIGGERS = (
    "initial",
    "menu",
    "banner",
    "bracket_match",
    "launch_intent",
    "scope_lost",
    "kicked_recover",
)


class HasActivityIdentity(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(request.auth, ActivityIdentity)


@api_view(["GET"])
@authentication_classes([ActivityAuthentication])
@permission_classes([HasActivityIdentity])
def activity_drafts(request: Request) -> Response:
    identity: ActivityIdentity = request.auth
    discord_user_id = str(identity.user.discordId or "")
    return Response(
        list_drafts(identity, discord_user_id),
        headers={"Cache-Control": "no-store"},
    )


class ActivityViewsThrottle(UserRateThrottle):
    scope = "activity_views"
    rate = "60/min"


class ViewRefInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("team", "hero", "bracket"))
    id = serializers.IntegerField(
        min_value=1, max_value=MAX_DATABASE_ID, required=False
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["kind"] == "bracket":
            if "id" in attrs:
                raise serializers.ValidationError("bracket takes no id")
        elif "id" not in attrs:
            raise serializers.ValidationError("id is required")
        return attrs


class ViewEventInput(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=("view", "notice_seen", "intent_declined", "open_external")
    )
    to = ViewRefInput(required=False)
    view = ViewRefInput(required=False)
    trigger = serializers.ChoiceField(choices=TRIGGERS, required=False)
    intent_id = serializers.CharField(max_length=32, required=False)

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        fields["from"] = ViewRefInput(required=False)
        return fields

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        action = attrs["action"]
        required: tuple[str, ...] = {
            "view": ("to", "trigger"),
            "notice_seen": (),
            "intent_declined": ("intent_id",),
            "open_external": ("view",),
        }[action]
        missing = [name for name in required if name not in attrs]
        if missing:
            raise serializers.ValidationError(
                {name: "This field is required." for name in missing}
            )
        return attrs


def _ref(ref: dict[str, Any] | None) -> tuple[str | None, int | None]:
    if ref is None:
        return None, None
    return ref["kind"], ref.get("id")


def _role(
    identity: ActivityIdentity, kind: str | None, draft_id: int | None
) -> Role | None:
    if kind in ("hero", "team") and draft_id is not None:
        return draft_role(identity.user, kind, draft_id)
    return None


def _in_scope(identity: ActivityIdentity, ref: dict[str, Any]) -> bool:
    kind, draft_id = _ref(ref)
    if kind == "bracket" or draft_id is None:
        return True
    return scope_allows(identity, kind, draft_id)


@api_view(["POST"])
@authentication_classes([ActivityAuthentication])
@permission_classes([HasActivityIdentity])
@throttle_classes([ActivityViewsThrottle])
def activity_views(request: Request) -> Response:
    identity: ActivityIdentity = request.auth
    payload = ViewEventInput(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data
    action = data["action"]
    discord_user_id = str(identity.user.discordId or "")
    common: dict[str, object] = {
        "system": "discord",
        "subsystem": "activity",
        "user_id": identity.user.pk,
        "discord_user_id": discord_user_id,
        "instance_id": identity.instance.instance_id,
        "guild_id": identity.instance.guild_id,
        "channel_id": identity.instance.channel_id,
        "tournament_id": identity.tournament_id,
    }
    target = data.get("to") if action == "view" else data.get("view")
    if action in ("view", "open_external") and not _in_scope(identity, target):
        kind, draft_id = _ref(target)
        log.warning(
            "activity_auth_rejected",
            **common,
            surface="views",
            reason="out_of_scope",
            code="activity_out_of_scope",
            kind=kind,
            draft_id=draft_id,
        )
        return Response(
            {"detail": OUT_OF_SCOPE, "code": "activity_out_of_scope"},
            status=status.HTTP_403_FORBIDDEN,
        )
    intent_id: str | None = data.get("intent_id")
    consumed = (
        consume_intent(discord_user_id, intent_id)
        if intent_id is not None and discord_user_id
        else False
    )
    if action == "view":
        from_kind, from_id = _ref(data.get("from"))
        to_kind, to_id = _ref(target)
        log.info(
            "activity_view_changed",
            **common,
            from_kind=from_kind,
            from_id=from_id,
            to_kind=to_kind,
            to_id=to_id,
            trigger=data["trigger"],
            role=_role(identity, to_kind, to_id),
            intent_id=intent_id,
            intent_consumed=consumed,
        )
    elif action == "notice_seen":
        log.info(
            "activity_notice_seen",
            **common,
            intent_id=intent_id,
            intent_consumed=consumed,
        )
    elif action == "intent_declined":
        kind, draft_id = _ref(target)
        log.info(
            "activity_intent_declined",
            **common,
            intent_id=intent_id,
            intent_consumed=consumed,
            kind=kind,
            draft_id=draft_id,
        )
    else:
        kind, view_id = _ref(target)
        log.info(
            "activity_open_external",
            **common,
            view_kind=kind,
            view_id=view_id,
            path=(
                None
                if kind != "hero" and identity.tournament_id is None
                else external_path(kind, view_id, identity.tournament_id)
            ),
        )
    return Response(status=status.HTTP_204_NO_CONTENT)
