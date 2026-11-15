"""Draft-scoped authentication shared by REST and Activity WebSockets."""

import re
from typing import Literal

from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    Scope,
)
from channels.db import database_sync_to_async
from django.conf import settings
from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from app.models import CustomUser, DraftRound
from discordbot.models import DraftActivityInstance

SALT = "discord-draft-activity-v1"
TOKEN_AGE = 12 * 60 * 60


def token_identity(token: str) -> tuple[CustomUser, DraftActivityInstance]:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        raise AuthenticationFailed("Discord Activities are disabled.")
    try:
        data = signing.loads(token.replace(".", ":"), salt=SALT, max_age=TOKEN_AGE)
        instance = DraftActivityInstance.objects.select_related("team_draft").get(
            instance_id=data["instance"]
        )
        user = CustomUser.objects.get(pk=data["user"], is_active=True)
        return user, instance
    except (
        signing.BadSignature,
        KeyError,
        TypeError,
        ValueError,
        DraftActivityInstance.DoesNotExist,
        CustomUser.DoesNotExist,
    ):
        raise AuthenticationFailed("Activity session expired. Reopen the Activity.")


def authenticate_token(
    token: str, draft_id: int, kind: Literal["hero", "team"]
) -> CustomUser:
    user, instance = token_identity(token)
    expected = instance.draft_id if kind == "hero" else instance.team_draft_id
    if expected != draft_id:
        raise AuthenticationFailed("Activity credentials belong to a different draft.")
    return user


class ActivityAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[CustomUser, None] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"draftactivity":
            return None
        if len(header) != 2:
            raise AuthenticationFailed("Invalid Activity credential.")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed("Invalid Activity credential.")
        user, instance = token_identity(token)
        path = request.path
        allowed = path == "/api/current_user"
        hero = re.fullmatch(r"/api/herodraft/(\d+)/(?:[a-z-]+/)?", path)
        team = re.fullmatch(r"/api/draft/(\d+)/(?:ready|start|pause|resume)/", path)
        if hero:
            allowed = instance.draft_id == int(hero[1])
        elif team:
            allowed = instance.team_draft_id == int(team[1])
        elif instance.team_draft_id and path == "/api/tournaments/pick_player":
            round_pk = request.data.get("draft_round_pk")
            if isinstance(round_pk, (int, str)) and str(round_pk).isdigit():
                allowed = DraftRound.objects.filter(
                    pk=round_pk, draft_id=instance.team_draft_id
                ).exists()
        if not allowed:
            raise AuthenticationFailed(
                "Activity credentials are only valid for this draft."
            )
        # Existing view-level captain/staff checks remain authoritative.
        return user, None


class ActivitySocketMiddleware:
    """Only the dedicated Activity socket accepts an Activity token."""

    def __init__(self, app: ASGI3Application, kind: Literal["hero", "team"]) -> None:
        self.app = app
        self.kind = kind

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        protocols = scope.get("subprotocols", [])
        token = (
            protocols[1]
            if len(protocols) == 2 and protocols[0] == "draftactivity"
            else ""
        )
        if not token:
            await send({"type": "websocket.close", "code": 4401})
            return
        try:
            user = await database_sync_to_async(
                authenticate_token, thread_sensitive=False
            )(token, scope["url_route"]["kwargs"]["draft_id"], self.kind)
        except AuthenticationFailed:
            await send({"type": "websocket.close", "code": 4401})
            return
        await self.app(dict(scope, user=user), receive, send)
