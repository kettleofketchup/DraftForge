"""Tournament-scoped authentication shared by REST and Activity WebSockets."""

import asyncio
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

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
from rest_framework.request import Request
from structlog.contextvars import bind_contextvars

from app.models import CustomUser, Draft, DraftRound, HeroDraft
from discordbot.activity_errors import ActivityAuthFailed
from discordbot.activity_roles import Role, draft_role
from discordbot.activity_targets import draft_tournament_id
from discordbot.models import DraftActivityChannel, DraftActivityInstance
from telemetry.logging import get_logger

log = get_logger(__name__)

SALT = "discord-draft-activity-v3"
# 0.14.x frames carry v2 draft tokens; remove after 0.15.
LEGACY_SALT = "discord-draft-activity-v2"
TOKEN_AGE = 12 * 60 * 60
SOCKET_REVALIDATE_SECONDS = 30
MAX_DATABASE_ID = (1 << 63) - 1
SESSION_EXPIRED = "Activity session expired. Reopen the Activity."
SOCKET_PROTOCOL = "draftactivity"
SESSION_ENDED_CODE = 4401
SCOPE_CLOSE_CODE = 4403


ActivityKind = Literal["hero", "team"]
SocketCloseReason = Literal["expired", "revoked", "out_of_scope", "disabled", "client"]
OUT_OF_SCOPE = "Activity credentials are only valid for this draft."
PATH_NOT_ALLOWED = "Activity credentials cannot use this endpoint."
HERO_SUFFIXES: frozenset[str] = frozenset(
    {
        "set-ready",
        "trigger-roll",
        "submit-choice",
        "submit-pick",
        "list-events",
        "list-available-heroes",
        "pause",
        "resume",
    }
)
IDENTITY_ONLY_PATHS: frozenset[str] = frozenset(
    {
        "/api/current_user",
        "/api/discord/activity/drafts/",
        "/api/discord/activity/views/",
    }
)
TEAM_DRAFT_SCOPED_PATHS: frozenset[str] = frozenset(
    {
        "/api/tournaments/pick_player",
        "/api/tournaments/undo-pick",
        "/api/draft/get-style-mmrs",
    }
)


class Pin(TypedDict):
    kind: ActivityKind
    draft: int


@dataclass(frozen=True)
class ActivityIdentity:
    user: CustomUser
    instance: DraftActivityInstance
    tournament_id: int | None
    pin: Pin | None

    @property
    def scope(self) -> Literal["tournament", "draft"]:
        return "draft" if self.tournament_id is None else "tournament"


def load_instance(pk: int, instance_id: str) -> DraftActivityInstance:
    return (
        DraftActivityInstance.objects.nocache()
        .select_related("draft__game", "team_draft")
        .get(pk=pk, instance_id=instance_id)
    )


def instance_tournament(instance: DraftActivityInstance) -> int | None:
    return draft_tournament_id(instance.draft or instance.team_draft)


def session_tournament(
    instance: DraftActivityInstance, *, channel_fallback: bool = True
) -> int | None:
    tournament_id = instance_tournament(instance)
    if tournament_id is not None or not channel_fallback:
        return tournament_id
    channel = (
        DraftActivityChannel.objects.nocache()
        .select_related("draft__game", "team_draft")
        .filter(guild_id=instance.guild_id, channel_id=instance.channel_id)
        .first()
    )
    if channel is None:
        return None
    return draft_tournament_id(channel.draft or channel.team_draft)


def instance_pin(instance: DraftActivityInstance) -> Pin:
    if instance.draft_id:
        return {"kind": "hero", "draft": instance.draft_id}
    return {"kind": "team", "draft": instance.team_draft_id}


def issue_activity_token(
    user: CustomUser, instance: DraftActivityInstance, *, channel_fallback: bool = True
) -> str:
    tournament_id = session_tournament(instance, channel_fallback=channel_fallback)
    return signing.dumps(
        {
            "user": user.pk,
            "binding": instance.pk,
            "instance": instance.instance_id,
            "tournament": tournament_id,
            "pin": None if tournament_id is not None else instance_pin(instance),
            "expires": time.time() + TOKEN_AGE,
        },
        salt=SALT,
    ).replace(":", ".")


def _is_id(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _pin(kind: object, draft: object) -> Pin:
    if not isinstance(draft, int) or not _is_id(draft):
        raise ValueError("invalid Activity pin")
    if kind == "hero":
        return {"kind": "hero", "draft": draft}
    if kind == "team":
        return {"kind": "team", "draft": draft}
    raise ValueError("invalid Activity pin")


def _load(token: str, salt: str) -> dict[str, Any]:
    data = signing.loads(token.replace(".", ":"), salt=salt, max_age=TOKEN_AGE)
    if data["expires"] <= time.time():
        raise signing.SignatureExpired("Activity credential expired")
    return data


def _token_data(token: str) -> dict[str, Any]:
    """Return a v3-shaped payload; a v2 payload gains ``legacy`` and a pin."""
    try:
        try:
            data = _load(token, SALT)
        except signing.SignatureExpired:
            raise
        except signing.BadSignature:
            data = _load(token, LEGACY_SALT)
            data = {
                "user": data["user"],
                "binding": data["binding"],
                "instance": data["instance"],
                "tournament": None,
                "pin": _pin(data["kind"], data["draft"]),
                "expires": data["expires"],
                "legacy": True,
            }
        tournament, pin = data["tournament"], data["pin"]
        if tournament is None:
            data["pin"] = _pin(pin["kind"], pin["draft"])
        elif not _is_id(tournament) or pin is not None:
            raise ValueError("invalid Activity scope")
        for key in ("user", "binding"):
            if not _is_id(data[key]):
                raise ValueError("invalid Activity identity")
        if not isinstance(data["instance"], str):
            raise ValueError("invalid Activity instance")
        return data
    except signing.SignatureExpired:
        raise ActivityAuthFailed("activity_session_ended", SESSION_EXPIRED, "expired")
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "bad_signature"
        )


def token_identity(token: str) -> ActivityIdentity:
    if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
        raise ActivityAuthFailed(
            "activity_disabled", "Discord Activities are disabled.", "disabled"
        )
    data = _token_data(token)
    try:
        instance = load_instance(data["binding"], data["instance"])
    except DraftActivityInstance.DoesNotExist:
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "instance_missing"
        )
    pin: Pin | None = data["pin"]
    if pin is not None and pin != instance_pin(instance):
        raise ActivityAuthFailed(
            "activity_session_ended",
            "Activity destination changed. Reopen the Activity.",
            "v2_mismatch" if data.get("legacy") else "pin_mismatch",
        )
    try:
        user = CustomUser.objects.nocache().get(pk=data["user"], is_active=True)
    except CustomUser.DoesNotExist:
        raise ActivityAuthFailed(
            "activity_session_ended", SESSION_EXPIRED, "inactive_user"
        )
    return ActivityIdentity(
        user=user, instance=instance, tournament_id=data["tournament"], pin=pin
    )


def scope_allows(identity: ActivityIdentity, kind: ActivityKind, draft_id: int) -> bool:
    tournament_id = identity.tournament_id
    if tournament_id is None:
        return identity.pin == {"kind": kind, "draft": draft_id}
    if kind == "hero":
        return (
            HeroDraft.objects.nocache()
            .filter(pk=draft_id, game__tournament_id=tournament_id)
            .exists()
        )
    return (
        Draft.objects.nocache()
        .filter(pk=draft_id, tournament_id=tournament_id)
        .exists()
    )


def _round_allowed(identity: ActivityIdentity, round_pk: int) -> bool:
    rounds = DraftRound.objects.nocache().filter(pk=round_pk)
    if identity.tournament_id is not None:
        return rounds.filter(draft__tournament_id=identity.tournament_id).exists()
    pin = identity.pin
    return (
        pin is not None
        and pin["kind"] == "team"
        and rounds.filter(draft_id=pin["draft"]).exists()
    )


def authenticate_token(
    token: str, draft_id: int, kind: ActivityKind
) -> ActivityIdentity:
    identity = token_identity(token)
    if not scope_allows(identity, kind, draft_id):
        raise ActivityAuthFailed("activity_out_of_scope", OUT_OF_SCOPE, "out_of_scope")
    return identity


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
    def authenticate(
        self, request: Request
    ) -> tuple[CustomUser, ActivityIdentity] | None:
        try:
            identity = self._identity(request)
        except ActivityAuthFailed as exc:
            log.warning(
                "activity_auth_rejected",
                system="discord",
                subsystem="activity",
                surface="rest",
                reason=exc.reason,
                code=exc.activity_code,
                path=request.path,
            )
            raise
        if identity is None:
            return None
        bind_contextvars(
            **{
                "user.id": identity.user.pk,
                "activity.instance_id": identity.instance.instance_id,
            }
        )
        # Existing view-level captain/staff checks remain authoritative.
        return identity.user, identity

    def _identity(self, request: Request) -> ActivityIdentity | None:
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
        identity = token_identity(token)
        path = request.path
        allowed = path in IDENTITY_ONLY_PATHS
        scoped = False
        hero = re.fullmatch(r"/api/herodraft/(\d+)/(?:([a-z-]+)/)?", path)
        team = re.fullmatch(r"/api/draft/(\d+)/(?:ready|start|pause|resume)/", path)
        if hero and (hero[2] is None or hero[2] in HERO_SUFFIXES):
            scoped = True
            draft_pk = _positive_id(hero[1])
            allowed = draft_pk is not None and scope_allows(identity, "hero", draft_pk)
        elif team:
            scoped = True
            draft_pk = _positive_id(team[1])
            allowed = draft_pk is not None and scope_allows(identity, "team", draft_pk)
        elif path in TEAM_DRAFT_SCOPED_PATHS:
            scoped = True
            data = request.data
            if isinstance(data, Mapping):
                if path == "/api/tournaments/pick_player":
                    round_pk = _positive_id(data.get("draft_round_pk"))
                    allowed = round_pk is not None and _round_allowed(
                        identity, round_pk
                    )
                else:
                    key = "draft_pk" if path == "/api/tournaments/undo-pick" else "pk"
                    draft_pk = _positive_id(data.get(key))
                    allowed = draft_pk is not None and scope_allows(
                        identity, "team", draft_pk
                    )
        if not allowed:
            raise ActivityAuthFailed(
                "activity_out_of_scope" if scoped else "activity_path_not_allowed",
                OUT_OF_SCOPE if scoped else PATH_NOT_ALLOWED,
                "out_of_scope" if scoped else "path_not_allowed",
            )
        return identity


class SocketActivity(TypedDict):
    instance_id: str
    tournament_id: int | None
    kind: ActivityKind
    draft_id: int
    role: Role


def _validate_socket(
    token: str, draft_id: int, kind: ActivityKind
) -> tuple[ActivityIdentity, Role]:
    identity = authenticate_token(token, draft_id, kind)
    return identity, draft_role(identity.user, kind, draft_id)


def _close_code(exc: ActivityAuthFailed) -> int:
    if exc.activity_code == "activity_out_of_scope":
        return SCOPE_CLOSE_CODE
    return SESSION_ENDED_CODE


def _close_reason(exc: ActivityAuthFailed) -> SocketCloseReason:
    if exc.activity_code == "activity_out_of_scope":
        return "out_of_scope"
    if exc.activity_code == "activity_disabled":
        return "disabled"
    if exc.reason == "expired":
        return "expired"
    return "revoked"


class _ActivitySessionEnded(Exception):
    """Unwind the existing consumer so its presence/disconnect cleanup still runs."""

    def __init__(self, close_code: int, reason: SocketCloseReason) -> None:
        super().__init__(reason)
        self.close_code = close_code
        self.reason: SocketCloseReason = reason


class ActivitySocketMiddleware:
    """Authenticate sockets, expire them, and periodically enforce revocation."""

    def __init__(self, app: ASGI3Application, kind: ActivityKind) -> None:
        self.app = app
        self.kind: ActivityKind = kind

    def _log_rejected(
        self,
        exc: ActivityAuthFailed,
        draft_id: int,
        identity: ActivityIdentity | None = None,
    ) -> None:
        log.warning(
            "activity_auth_rejected",
            system="discord",
            subsystem="activity",
            surface="socket",
            kind=self.kind,
            draft_id=draft_id,
            reason=exc.reason,
            code=exc.activity_code,
            user_id=identity.user.pk if identity else None,
            instance_id=identity.instance.instance_id if identity else None,
            tournament_id=identity.tournament_id if identity else None,
        )

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        protocols = scope.get("subprotocols", [])
        offered = bool(protocols) and protocols[0] == SOCKET_PROTOCOL
        token = protocols[1] if offered and len(protocols) == 2 else ""
        draft_id: int = scope["url_route"]["kwargs"]["draft_id"]

        async def reject(code: int) -> None:
            # A pre-accept close reaches the browser as a bare handshake
            # failure; accept first so the client sees the close code.
            if offered:
                await send({"type": "websocket.accept", "subprotocol": SOCKET_PROTOCOL})
            await send({"type": "websocket.close", "code": code})

        if not token:
            self._log_rejected(
                ActivityAuthFailed(
                    "activity_session_ended", SESSION_EXPIRED, "bad_signature"
                ),
                draft_id,
            )
            await reject(SESSION_ENDED_CODE)
            return
        validate = database_sync_to_async(_validate_socket, thread_sensitive=False)
        try:
            identity, role = await validate(token, draft_id, self.kind)
            expires_at = _token_data(token)["expires"]
        except ActivityAuthFailed as exc:
            self._log_rejected(exc, draft_id)
            await reject(_close_code(exc))
            return
        started = time.monotonic()
        next_validation = started + SOCKET_REVALIDATE_SECONDS
        validation_lock = asyncio.Lock()
        last_close_code: int | None = None

        async def check_session() -> None:
            nonlocal next_validation, role
            if time.time() >= expires_at:
                raise _ActivitySessionEnded(SESSION_ENDED_CODE, "expired")
            if time.monotonic() < next_validation:
                return
            async with validation_lock:
                if time.monotonic() < next_validation:
                    return
                try:
                    _, role = await validate(token, draft_id, self.kind)
                except ActivityAuthFailed as exc:
                    self._log_rejected(exc, draft_id, identity)
                    raise _ActivitySessionEnded(_close_code(exc), _close_reason(exc))
                next_validation = time.monotonic() + SOCKET_REVALIDATE_SECONDS

        async def guarded_receive() -> Any:
            nonlocal last_close_code
            while True:
                await check_session()
                timeout = min(
                    expires_at - time.time(), next_validation - time.monotonic()
                )
                if timeout <= 0:
                    continue
                try:
                    message = await asyncio.wait_for(receive(), timeout=timeout)
                except TimeoutError:
                    # Revalidate even if the client is idle or has stopped heartbeats.
                    continue
                if message["type"] == "websocket.disconnect":
                    last_close_code = message.get("code")
                    return message
                await check_session()
                return message

        async def guarded_send(message: Any) -> None:
            nonlocal last_close_code
            if message["type"] == "websocket.accept":
                # Browsers fail the handshake unless one offered protocol is echoed.
                message = {**message, "subprotocol": SOCKET_PROTOCOL}
            elif message["type"] == "websocket.close":
                last_close_code = message.get("code", 1000)
            else:
                await check_session()
            await send(message)

        def log_closed(close_code: int | None, reason: SocketCloseReason) -> None:
            log.info(
                "activity_socket_closed",
                system="discord",
                subsystem="activity",
                kind=self.kind,
                draft_id=draft_id,
                role=role,
                close_code=close_code,
                reason=reason,
                duration_s=round(time.monotonic() - started, 3),
                user_id=identity.user.pk,
                instance_id=identity.instance.instance_id,
                tournament_id=identity.tournament_id,
            )

        activity: SocketActivity = {
            "instance_id": identity.instance.instance_id,
            "tournament_id": identity.tournament_id,
            "kind": self.kind,
            "draft_id": draft_id,
            "role": role,
        }
        try:
            await self.app(
                dict(scope, user=identity.user, activity=activity),
                guarded_receive,
                guarded_send,
            )
        except _ActivitySessionEnded as ended:
            log_closed(ended.close_code, ended.reason)
            await send({"type": "websocket.close", "code": ended.close_code})
            return
        log_closed(last_close_code, "client")
