"""Draft-scoped authentication shared by REST and Activity WebSockets."""

import asyncio
import re
import time
from collections.abc import Mapping
from typing import Any, Literal

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
from discordbot.activity_errors import ActivityAuthFailed
from discordbot.models import DraftActivityInstance

SALT = "discord-draft-activity-v2"
TOKEN_AGE = 12 * 60 * 60
SOCKET_REVALIDATE_SECONDS = 30
MAX_DATABASE_ID = (1 << 63) - 1
SESSION_EXPIRED = "Activity session expired. Reopen the Activity."
SOCKET_PROTOCOL = "draftactivity"
SESSION_ENDED_CODE = 4401


def issue_activity_token(user: CustomUser, instance: DraftActivityInstance) -> str:
    """Sign the immutable binding identity and destination, not a reusable instance ID."""
    return signing.dumps(
        {
            "user": user.pk,
            "binding": instance.pk,
            "instance": instance.instance_id,
            "kind": "hero" if instance.draft_id else "team",
            "draft": instance.draft_id or instance.team_draft_id,
            "expires": time.time() + TOKEN_AGE,
        },
        salt=SALT,
    ).replace(":", ".")


def _token_data(token: str) -> dict[str, Any]:
    try:
        data = signing.loads(token.replace(".", ":"), salt=SALT, max_age=TOKEN_AGE)
        if data["expires"] <= time.time():
            raise signing.SignatureExpired("Activity credential expired")
        return data
    except signing.SignatureExpired:
        raise ActivityAuthFailed("activity_session_ended", SESSION_EXPIRED, "expired")
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "bad_signature"
        )


def token_identity(token: str) -> tuple[CustomUser, DraftActivityInstance]:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        raise ActivityAuthFailed(
            "activity_disabled", "Discord Activities are disabled.", "disabled"
        )
    data = _token_data(token)
    try:
        instance = DraftActivityInstance.objects.select_related("team_draft").get(
            pk=data["binding"], instance_id=data["instance"]
        )
        kind = "hero" if instance.draft_id else "team"
        if data["kind"] != kind or data["draft"] != (
            instance.draft_id or instance.team_draft_id
        ):
            raise ActivityAuthFailed(
                "activity_session_ended",
                "Activity destination changed. Reopen the Activity.",
                "v2_mismatch",
            )
        # Authorization must observe deactivation immediately, even when an
        # administrative bulk update leaves a cached active-user query behind.
        user = CustomUser.objects.nocache().get(pk=data["user"], is_active=True)
        return user, instance
    except (KeyError, TypeError, ValueError):
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "bad_signature"
        )
    except DraftActivityInstance.DoesNotExist:
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "instance_missing"
        )
    except CustomUser.DoesNotExist:
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "inactive_user"
        )


def authenticate_token(
    token: str, draft_id: int, kind: Literal["hero", "team"]
) -> CustomUser:
    user, instance = token_identity(token)
    expected = instance.draft_id if kind == "hero" else instance.team_draft_id
    if expected != draft_id:
        raise ActivityAuthFailed(
            "activity_out_of_scope",
            "Activity credentials belong to a different draft.",
            "out_of_scope",
        )
    return user


def _positive_id(value: object) -> int | None:
    """Reject non-integers and out-of-range IDs before reaching the database adapter."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        if len(value) > 19 or not value.isascii() or not value.isdecimal():
            return None
        value = int(value)
    if isinstance(value, int) and 0 < value <= MAX_DATABASE_ID:
        return value
    return None


class ActivityAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[CustomUser, None] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"draftactivity":
            return None
        if len(header) != 2:
            raise ActivityAuthFailed(
                "activity_session_ended",
                "Invalid Activity credential.",
                "bad_signature",
            )
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError:
            raise ActivityAuthFailed(
                "activity_session_ended",
                "Invalid Activity credential.",
                "bad_signature",
            )
        user, instance = token_identity(token)
        path = request.path
        allowed = path == "/api/current_user"
        scoped = False
        hero = re.fullmatch(r"/api/herodraft/(\d+)/(?:[a-z-]+/)?", path)
        team = re.fullmatch(r"/api/draft/(\d+)/(?:ready|start|pause|resume)/", path)
        if hero:
            scoped = True
            draft_pk = _positive_id(hero[1])
            allowed = draft_pk is not None and instance.draft_id == draft_pk
        elif team:
            scoped = True
            draft_pk = _positive_id(team[1])
            allowed = draft_pk is not None and instance.team_draft_id == draft_pk
        elif instance.team_draft_id and path in {
            "/api/tournaments/pick_player",
            "/api/tournaments/undo-pick",
            "/api/draft/get-style-mmrs",
        }:
            scoped = True
            data = request.data
            if isinstance(data, Mapping):
                if path == "/api/tournaments/pick_player":
                    round_pk = _positive_id(data.get("draft_round_pk"))
                    allowed = (
                        round_pk is not None
                        and DraftRound.objects.filter(
                            pk=round_pk, draft_id=instance.team_draft_id
                        ).exists()
                    )
                else:
                    key = "draft_pk" if path == "/api/tournaments/undo-pick" else "pk"
                    allowed = instance.team_draft_id == _positive_id(data.get(key))
        if not allowed:
            raise ActivityAuthFailed(
                "activity_out_of_scope" if scoped else "activity_path_not_allowed",
                "Activity credentials are only valid for this draft.",
                "out_of_scope" if scoped else "path_not_allowed",
            )
        # Existing view-level captain/staff checks remain authoritative.
        return user, None


class _ActivitySessionEnded(Exception):
    """Unwind the existing consumer so its presence/disconnect cleanup still runs."""


class ActivitySocketMiddleware:
    """Authenticate sockets, expire them, and periodically enforce revocation."""

    def __init__(self, app: ASGI3Application, kind: Literal["hero", "team"]) -> None:
        self.app = app
        self.kind = kind

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        protocols = scope.get("subprotocols", [])
        offered = bool(protocols) and protocols[0] == SOCKET_PROTOCOL
        token = protocols[1] if offered and len(protocols) == 2 else ""

        async def reject() -> None:
            # A pre-accept close reaches the browser as a bare handshake
            # failure; accept first so the client sees 4401 and re-authenticates.
            if offered:
                await send({"type": "websocket.accept", "subprotocol": SOCKET_PROTOCOL})
            await send({"type": "websocket.close", "code": SESSION_ENDED_CODE})

        if not token:
            await reject()
            return
        draft_id = scope["url_route"]["kwargs"]["draft_id"]
        validate = database_sync_to_async(authenticate_token, thread_sensitive=False)
        try:
            user = await validate(token, draft_id, self.kind)
            expires_at = _token_data(token)["expires"]
        except AuthenticationFailed:
            await reject()
            return
        next_validation = time.monotonic() + SOCKET_REVALIDATE_SECONDS
        validation_lock = asyncio.Lock()

        async def check_session() -> None:
            nonlocal next_validation
            if time.time() >= expires_at:
                raise _ActivitySessionEnded
            if time.monotonic() < next_validation:
                return
            async with validation_lock:
                if time.monotonic() < next_validation:
                    return
                try:
                    await validate(token, draft_id, self.kind)
                except AuthenticationFailed:
                    raise _ActivitySessionEnded
                next_validation = time.monotonic() + SOCKET_REVALIDATE_SECONDS

        async def guarded_receive() -> Any:
            while True:
                await check_session()
                timeout = min(
                    expires_at - time.time(), next_validation - time.monotonic()
                )
                if timeout <= 0:
                    continue
                try:
                    message = await asyncio.wait_for(receive(), timeout=timeout)
                    await check_session()
                    return message
                except TimeoutError:
                    # Revalidate even if the client is idle or has stopped heartbeats.
                    continue

        async def guarded_send(message: Any) -> None:
            if message["type"] == "websocket.accept":
                # Browsers fail the handshake unless one offered protocol is echoed.
                message = {**message, "subprotocol": SOCKET_PROTOCOL}
            elif message["type"] != "websocket.close":
                await check_session()
            await send(message)

        try:
            await self.app(dict(scope, user=user), guarded_receive, guarded_send)
        except _ActivitySessionEnded:
            await send({"type": "websocket.close", "code": SESSION_ENDED_CODE})
