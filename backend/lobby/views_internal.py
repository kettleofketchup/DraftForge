"""Internal API for the lobby Celery tasks, and the dota_lobby webhook receiver.

Mounted under `api/internal/lobbies/` and authenticated with X-Internal-Token
(InternalServiceAuth: token plus IP allowlist). Celery workers never touch the
database: they claim a lobby here, call dota_lobby, and report back here.

The webhook receiver (`events/`) also verifies dota_lobby's HMAC signature
over the raw body. The signature is the real protection: the IP allowlist
trusts the first X-Forwarded-For value.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.models import Game
from lobby import broadcast, events, refs, services, states
from lobby.models import GameLobby, GameLobbyEvent
from lobby.passwords import PasswordKeyUnavailable
from lobby.schemas import LobbyEvent, LobbyView
from lobby.webhook import verify_signature
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]
_LOG_API = {"system": "lobby", "subsystem": "api"}
_LOG_WEBHOOK = {"system": "lobby", "subsystem": "webhook"}


def _error(message: str, code: str, http_status: int, **extra: Any) -> Response:
    return Response({"error": message, "code": code, **extra}, status=http_status)


def _view_from(data: object) -> LobbyView | None:
    """A LobbyView from a request body, with any password dropped."""
    if not isinstance(data, dict):
        return None
    data = {k: v for k, v in data.items() if k != "password"}
    try:
        return LobbyView.model_validate(data)
    except ValidationError:
        return None


def _row_summary(row: GameLobby) -> dict[str, Any]:
    return {
        "id": row.pk,
        "game_id": row.game_id,
        "lobby_id": row.lobby_id,
        "external_ref": row.external_ref,
        "state": row.state,
        "ended": row.ended,
        "trigger": row.trigger,
        "last_seq": row.last_seq,
        "age_seconds": int((timezone.now() - row.created_at).total_seconds()),
        "radiant_team_ref": (
            services.team_ref(row.radiant_team_id) if row.radiant_team_id else None
        ),
        "dire_team_ref": (
            services.team_ref(row.dire_team_id) if row.dire_team_id else None
        ),
        "wants_flip": services.wants_flip(row),
    }


def _record_accepted(row: GameLobby, view: LobbyView) -> bool:
    """Bind the dota_lobby lobby to `row`. True when it must be closed again.

    A row DraftForge ended while the create was in flight (the game's teams
    changed) keeps the lobby ID, so its events still find it, but the lobby
    is closed.
    """
    if row.lobby_id and row.lobby_id != view.id:
        raise ValueError("lobby_id_mismatch")
    if not row.lobby_id:
        row.lobby_id = view.id
        row.accepted_at = timezone.now()
        row.save(update_fields=["lobby_id", "accepted_at", "updated_at"])
    if row.ended:
        return True
    row.last_error_code = ""
    row.last_error_detail = ""
    events.apply_snapshot(row, view)
    broadcast.lobby_changed_on_commit(row, bracket_changed=False)
    return False


# ---------------------------------------------------------------------------
# Celery-facing endpoints
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def eligible_games(request: Request) -> Response:
    """Games that should get a lobby automatically and have none."""
    return Response([{"id": g.pk} for g in services.auto_eligible_games()])


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def claim(request: Request, game_id: int) -> Response:
    """The game's active lobby, or a new one, with the create body to send.

    Body: `{trigger, user_id?, allow_missing?}`. The create body includes the
    lobby password and is returned only while the lobby is `requested`.
    """
    get_object_or_404(Game, pk=game_id)
    trigger = request.data.get("trigger") or GameLobby.Trigger.AUTO
    if trigger not in GameLobby.Trigger.values:
        return _error("Unknown trigger", "invalid_trigger", 400)
    user_id = request.data.get("user_id")
    result = services.claim_lobby(
        game_id,
        trigger=trigger,
        user_id=user_id if isinstance(user_id, int) else None,
        allow_missing=request.data.get("allow_missing") is True,
    )
    row = result.game_lobby
    if row is None:
        eligibility = result.eligibility
        return _error(
            "Game is not eligible for a lobby",
            eligibility.code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=eligibility.details,
        )
    payload: dict[str, Any] = {
        "game_lobby_id": row.pk,
        "external_ref": row.external_ref,
        "created": result.created,
        "lobby_id": row.lobby_id,
        "state": row.state,
    }
    if row.state == states.REQUESTED and not row.lobby_id:
        try:
            payload["body"] = services.create_body(row)
        except (PasswordKeyUnavailable, ImproperlyConfigured) as exc:
            log.error(
                "lobby_password_unavailable",
                game_lobby_id=row.pk,
                error=type(exc).__name__,
                **_LOG_API,
            )
            return _error("Lobby password unavailable", "password_unavailable", 503)
    if result.created:
        log.info(
            "lobby_claimed",
            game_id=game_id,
            game_lobby_id=row.pk,
            trigger=trigger,
            **_LOG_API,
        )
        broadcast.lobby_changed_on_commit(row, bracket_changed=False)
    return Response(payload, status=201 if result.created else 200)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def accepted(request: Request, pk: int) -> Response:
    """dota_lobby accepted the create (202) or replayed it (200).

    Body: `{lobby: LobbyView}`. Answers `{close: true}` when DraftForge ended
    the row meanwhile and the lobby has to be closed.
    """
    view = _view_from(request.data.get("lobby"))
    if view is None:
        return _error("Invalid lobby", "invalid_lobby", 400)
    with transaction.atomic():
        row = get_object_or_404(GameLobby.objects.select_for_update(), pk=pk)
        try:
            close = _record_accepted(row, view)
        except ValueError:
            return _error("Lobby ID mismatch", "lobby_id_mismatch", 409)
    log.info(
        "lobby_accepted",
        game_lobby_id=pk,
        lobby_id=view.id,
        state=view.state,
        replayed=request.data.get("replayed") is True,
        close=close,
        **_LOG_API,
    )
    return Response({"close": close})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def rejected(request: Request, pk: int) -> Response:
    """The create failed. Body: `{code, detail, retryable}`.

    A retryable failure keeps the row `requested` (the reconcile task tries
    again); any other ends it with state `error`, for organizers to retry.
    """
    code = str(request.data.get("code") or "unknown")[:48]
    detail = str(request.data.get("detail") or "")
    retryable = request.data.get("retryable") is True
    with transaction.atomic():
        row = get_object_or_404(GameLobby.objects.select_for_update(), pk=pk)
        row.last_error_code = code
        row.last_error_detail = detail
        row.last_error_at = timezone.now()
        fields = ["last_error_code", "last_error_detail", "last_error_at"]
        if not retryable and not row.ended and not row.lobby_id:
            row.state = states.ERROR
            row.state_reason = code[:64]
            fields += ["state", "state_reason"]
        row.save(update_fields=[*fields, "updated_at"])
        broadcast.lobby_changed_on_commit(row, bracket_changed=False)
    return Response({"state": row.state})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def conflict(request: Request, pk: int) -> Response:
    """dota_lobby answered 409 conflict: another active lobby has our ref.

    Body: `{lobby: LobbyView}`, the active lobby holding the ref. Answers
    `{action}`:

    - `adopt`: it is this row's lobby (a create whose answer was lost); it is
      recorded as accepted, and `close` says whether to close it again;
    - `close_and_retry`: it belongs to an earlier lobby of this game that
      DraftForge already ended; close it, then create again;
    - `reject`: someone else's lobby; the row ends with `conflict`.
    """
    view = _view_from(request.data.get("lobby"))
    if view is None:
        return _error("Invalid lobby", "invalid_lobby", 400)
    with transaction.atomic():
        row = get_object_or_404(GameLobby.objects.select_for_update(), pk=pk)
        owner = view.metadata.get("game_lobby_id", "")
        if view.external_ref == row.external_ref and owner == str(row.pk):
            try:
                close = _record_accepted(row, view)
            except ValueError:
                return _error("Lobby ID mismatch", "lobby_id_mismatch", 409)
            action: dict[str, Any] = {"action": "adopt", "close": close}
        elif (
            view.external_ref == row.external_ref
            and GameLobby.objects.filter(game_id=row.game_id, ended=True)
            .filter(pk=int(owner) if owner.isdigit() else -1)
            .exists()
        ) or GameLobby.objects.filter(
            game_id=row.game_id, ended=True, lobby_id=view.id
        ).exists():
            action = {"action": "close_and_retry"}
        else:
            if not row.ended and not row.lobby_id:
                row.state = states.ERROR
                row.state_reason = "conflict"
            row.last_error_code = "conflict"
            row.last_error_detail = (
                f"external_ref {row.external_ref} is held by lobby {view.id}"
            )
            row.last_error_at = timezone.now()
            row.save()
            broadcast.lobby_changed_on_commit(row, bracket_changed=False)
            action = {"action": "reject"}
    log.info(
        "lobby_create_conflict",
        game_lobby_id=pk,
        other_lobby_id=view.id,
        action=action["action"],
        **_LOG_API,
    )
    return Response(action)


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def active(request: Request) -> Response:
    """Every lobby that has not ended, for the reconcile task."""
    rows = GameLobby.objects.filter(ended=False).select_related("game").order_by("pk")
    return Response([_row_summary(row) for row in rows])


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def detail(request: Request, pk: int) -> Response:
    row = get_object_or_404(GameLobby.objects.select_related("game"), pk=pk)
    return Response(_row_summary(row))


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def sync(request: Request, pk: int) -> Response:
    """Apply what the reconcile task read from dota_lobby.

    Body: `{lobby: LobbyView | null, events: [envelope, ...], missing: bool}`.
    Events go through the same path as webhooks; the snapshot is applied
    when it is not behind them. `missing` means dota_lobby no longer knows
    the lobby: the row ends as `closed` / `not_found`.
    """
    raw_events = request.data.get("events") or []
    if not isinstance(raw_events, list):
        return _error("events must be a list", "invalid_events", 400)
    parsed: list[tuple[LobbyEvent, dict]] = []
    for raw in raw_events:
        try:
            parsed.append((LobbyEvent.model_validate(raw), raw))
        except ValidationError:
            return _error("Invalid event", "invalid_event", 400)
    view = None
    if request.data.get("lobby") is not None:
        view = _view_from(request.data.get("lobby"))
        if view is None:
            return _error("Invalid lobby", "invalid_lobby", 400)

    with transaction.atomic():
        row = get_object_or_404(
            GameLobby.objects.select_for_update().select_related("game"), pk=pk
        )
        if row.lobby_id and any(e.lobby.id != row.lobby_id for e, _ in parsed):
            return _error("Event for another lobby", "lobby_id_mismatch", 409)
        if view is not None and row.lobby_id and view.id != row.lobby_id:
            return _error("Lobby ID mismatch", "lobby_id_mismatch", 409)
        result = events.ingest_events(row, parsed, source=GameLobbyEvent.Source.POLL)
        snapshot = False
        if view is not None:
            snapshot = events.apply_snapshot(row, view)
        elif request.data.get("missing") is True and not row.ended:
            row.state = states.CLOSED
            row.state_reason = "not_found"
            row.save(update_fields=["state", "state_reason", "updated_at"])
            snapshot = True
        else:
            row.last_synced_at = timezone.now()
            row.save(update_fields=["last_synced_at", "updated_at"])
        if snapshot and not result.applied:
            broadcast.lobby_changed_on_commit(row, bracket_changed=False)
    return Response(
        {
            "applied": result.applied,
            "duplicates": result.duplicates,
            "gap": result.gap,
            "last_seq": row.last_seq,
            "state": row.state,
        }
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def notify_info(request: Request, pk: int) -> Response:
    """Who to DM about a lobby, for the opt-in lobby info message.

    No password: the worker reads the live one from dota_lobby.
    """
    from app.models import CustomUser

    row = get_object_or_404(
        GameLobby.objects.select_related(
            "game__tournament", "radiant_team", "dire_team"
        ),
        pk=pk,
    )
    tournament = row.game.tournament
    recipients = []
    for side, team in (("radiant", row.radiant_team), ("dire", row.dire_team)):
        if team is None:
            continue
        member_ids = [u.pk for u in services.team_roster(team)]
        users = (
            CustomUser.objects.filter(pk__in=member_ids, discordId__isnull=False)
            .exclude(discordId="")
            .order_by("pk")
        )
        recipients.extend(
            {
                "user_pk": u.pk,
                "discord_id": u.discordId,
                "username": u.username or "",
                "side": side,
                "team_name": team.name,
            }
            for u in users
        )
    return Response(
        {
            "game_lobby_id": row.pk,
            "game_id": row.game_id,
            "lobby_id": row.lobby_id,
            "ended": row.ended,
            "tournament_id": tournament.pk if tournament else None,
            "tournament_name": tournament.name if tournament else "",
            "enabled": bool(tournament and tournament.discord_send_lobby_info),
            "name": str(row.request.get("name") or ""),
            "region": str(row.request.get("region") or ""),
            "radiant_name": row.radiant_team.name if row.radiant_team else "",
            "dire_name": row.dire_team.name if row.dire_team else "",
            "recipients": recipients,
        }
    )


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------


def _find_row(event: LobbyEvent) -> GameLobby | None:
    """The row an event belongs to, binding the lobby ID on first contact."""
    row = (
        GameLobby.objects.select_for_update()
        .select_related("game")
        .filter(lobby_id=event.lobby.id)
        .first()
    )
    if row is not None:
        return row
    game_pk = refs.parse_external_ref(
        event.lobby.external_ref, settings.DOTA_LOBBY_REF_PREFIX
    )
    owner = event.lobby.metadata.get("game_lobby_id", "")
    if game_pk is None or not owner.isdigit():
        return None
    row = (
        GameLobby.objects.select_for_update()
        .select_related("game")
        .filter(
            pk=int(owner),
            game_id=game_pk,
            external_ref=event.lobby.external_ref,
            lobby_id__isnull=True,
        )
        .first()
    )
    if row is not None:
        # The create's answer has not been recorded yet. Bind now, so a later
        # backfill can read this lobby's events.
        row.lobby_id = event.lobby.id
        row.accepted_at = timezone.now()
        row.save(update_fields=["lobby_id", "accepted_at", "updated_at"])
    return row


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def webhook_events(request: Request) -> Response:
    """POST /api/internal/lobbies/events/: one signed dota_lobby event.

    Answers 2xx for everything dota_lobby should not send again (applied,
    duplicate, out of order, a lobby that is not ours), 401 for a bad
    signature (given up at once), 400 for a malformed envelope, and 503 while
    lobbies are disabled or no secret is configured (retried for 24 h).
    """
    # The signature covers the raw bytes: read them before anything parses.
    raw = request.body
    secrets = tuple(getattr(settings, "DOTA_LOBBY_WEBHOOK_SECRETS", ()) or ())
    if not services.is_enabled() or not secrets:
        reason = "lobby_disabled" if not services.is_enabled() else "no_secret"
        log.warning("lobby_webhook_unavailable", reason=reason, **_LOG_WEBHOOK)
        resp = _error("Lobby webhooks are not configured", reason, 503)
        resp["Retry-After"] = "300"
        return resp

    if not verify_signature(
        secrets,
        request.headers.get("X-Dota-Lobby-Timestamp"),
        request.headers.get("X-Dota-Lobby-Signature"),
        raw,
        tolerance_seconds=settings.DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS,
    ):
        log.warning(
            "lobby_webhook_bad_signature",
            event_id=request.headers.get("X-Dota-Lobby-Event-Id", "")[:64],
            **_LOG_WEBHOOK,
        )
        return _error("Bad signature", "bad_signature", 401)

    try:
        envelope = json.loads(raw)
        event = LobbyEvent.model_validate(envelope)
    except (ValueError, ValidationError):
        log.warning("lobby_webhook_malformed", **_LOG_WEBHOOK)
        return _error("Malformed event", "invalid_event", 400)

    with transaction.atomic():
        row = _find_row(event)
        if row is None:
            log.info(
                "lobby_webhook_ignored",
                event_id=event.id,
                lobby_id=event.lobby.id,
                external_ref=event.lobby.external_ref,
                **_LOG_WEBHOOK,
            )
            return Response({"status": "ignored"})
        result = events.ingest_events(
            row, [(event, envelope)], source=GameLobbyEvent.Source.WEBHOOK
        )
        if result.gap:
            from lobby.tasks import backfill_lobby_events

            pk = row.pk
            transaction.on_commit(lambda: backfill_lobby_events.delay(pk))

    if result.duplicates:
        outcome = "duplicate"
    elif result.gap and not result.applied:
        outcome = "queued"
    else:
        outcome = "applied"
    log.info(
        "lobby_webhook_received",
        event_id=event.id,
        event_type=event.type,
        seq=event.seq,
        lobby_id=event.lobby.id,
        outcome=outcome,
        applied=result.applied,
        **_LOG_WEBHOOK,
    )
    return Response({"status": outcome, "last_seq": row.last_seq})
