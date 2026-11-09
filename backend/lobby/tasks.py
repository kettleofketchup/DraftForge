"""Celery tasks that talk to dota_lobby.

Like every DraftForge task they never touch the database: they read and
write through the internal lobby API (lobby.internal_api) and call dota_lobby
with lobby.client. Every task does nothing while DOTA_LOBBY_ENABLED is off.

- create_dota_lobby: claim a lobby for a game, send the create, report back.
  Create is idempotent on external_ref, so it is safe to repeat.
- reconcile_dota_lobbies (beat, every 60 s): catch up on anything webhooks
  missed, resend creates that never got an answer and are no longer being
  retried (the backend's `resend_due`), flip sides the hero draft
  decided, finish closes dota_lobby has not confirmed (`close_pending`),
  and create lobbies for games that should have one.
- backfill_lobby_events: read the events a webhook gap skipped.
- close_dota_lobby, flip_lobby_sides: one dota_lobby action each.
- send_lobby_info: the opt-in Discord DM with the lobby name and password.

Only errors dota_lobby marks retryable (503, 504, timeouts, connection
errors) are retried; any other is reported to the backend as permanent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from celery import Task, shared_task
from django.conf import settings

from lobby import internal_api
from lobby.client import DotaLobbyClient, DotaLobbyError
from lobby.schemas import LobbyView
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG_TASKS = {"system": "lobby", "subsystem": "tasks"}
_LOG_RECONCILE = {"system": "lobby", "subsystem": "reconcile"}

CONFLICT_RETRY_SECONDS = 15
# Close answers meaning there is nothing left to close.
CLOSE_DONE_CODES = frozenset({"not_found", "invalid_state"})
MAX_RETRY_COUNTDOWN = 600


def _enabled() -> bool:
    return bool(getattr(settings, "DOTA_LOBBY_ENABLED", False))


def _view_json(view: LobbyView) -> dict[str, Any]:
    return view.model_dump(mode="json", exclude={"password"})


def _countdown(retries: int) -> int:
    return min(30 * 2**retries, MAX_RETRY_COUNTDOWN)


@shared_task(bind=True, max_retries=5)
def create_dota_lobby(
    self: Task,
    game_id: int,
    trigger: str = "auto",
    user_id: int | None = None,
    allow_missing: bool = False,
    game_lobby_id: int | None = None,
) -> str:
    """Create (or resend the create of) the game's lobby in dota_lobby.

    Without `game_lobby_id` the task claims the game's active lobby or a new
    row. Every retry carries the claimed row's ID, so a row that ended in
    the meantime (an organizer closed or replaced it) stops the task instead
    of being followed by a fresh lobby.
    """
    if not _enabled():
        return "disabled"
    status, claim = internal_api.claim(
        game_id,
        trigger=trigger,
        user_id=user_id,
        allow_missing=allow_missing,
        game_lobby_id=game_lobby_id,
    )
    if status is None or status >= 500 and status != 503:
        raise self.retry(countdown=_countdown(self.request.retries))
    if status == 503 or claim is None:
        log.error("lobby_claim_failed", game_id=game_id, status=status, **_LOG_TASKS)
        return "claim_failed"
    if status >= 400:
        log.info(
            "lobby_create_skipped",
            game_id=game_id,
            game_lobby_id=game_lobby_id,
            reason=claim.get("code"),
            trigger=trigger,
            **_LOG_TASKS,
        )
        return str(claim.get("code") or "not_eligible")
    pk = claim["game_lobby_id"]
    body = claim.get("body")
    if body is None:
        return "exists"

    def retry(countdown: int) -> Exception:
        return self.retry(
            args=[game_id],
            kwargs={
                "trigger": trigger,
                "user_id": user_id,
                "allow_missing": allow_missing,
                "game_lobby_id": pk,
            },
            countdown=countdown,
        )

    try:
        client = DotaLobbyClient()
        result = client.create_lobby(body)
    except DotaLobbyError as exc:
        return _create_failed(self, retry, pk, body, exc)

    answer = internal_api.accepted(
        pk, _view_json(result.lobby), replayed=result.replayed
    )
    log.info(
        "lobby_created",
        game_id=game_id,
        game_lobby_id=pk,
        lobby_id=result.lobby.id,
        replayed=result.replayed,
        **_LOG_TASKS,
    )
    if answer and answer.get("close"):
        _close(client, pk, result.lobby.id)
        return "closed"
    return "replayed" if result.replayed else "created"


RetryFn = Callable[[int], Exception]


def _create_failed(
    task: Any, retry: RetryFn, pk: int, body: dict[str, Any], exc: DotaLobbyError
) -> str:
    log_kwargs = {
        "game_lobby_id": pk,
        "code": exc.code,
        "http_status_code": exc.status,
        "retryable": exc.retryable,
        **_LOG_TASKS,
    }
    if exc.retryable:
        will_retry = task.request.retries < task.max_retries
        countdown = (
            max(exc.retry_after or 0, _countdown(task.request.retries))
            if will_retry
            else 0
        )
        internal_api.rejected(
            pk,
            code=exc.code,
            detail=exc.detail,
            retryable=True,
            retry_in=countdown,
        )
        if will_retry:
            log.info(
                "lobby_create_retry", attempt=task.request.retries + 1, **log_kwargs
            )
            raise retry(countdown)
        # Left `requested`: the reconcile task sends it again later.
        log.warning("lobby_create_retries_exhausted", **log_kwargs)
        return exc.code
    if exc.code == "conflict":
        return _resolve_conflict(task, retry, pk, body)
    log.warning(
        "lobby_create_refused",
        errors=[e.model_dump(mode="json") for e in exc.errors],
        **log_kwargs,
    )
    internal_api.rejected(pk, code=exc.code, detail=exc.detail, retryable=False)
    return exc.code


def _resolve_conflict(task: Task, retry: RetryFn, pk: int, body: dict[str, Any]) -> str:
    """Another active lobby holds our external_ref: adopt, replace or give up."""
    client = DotaLobbyClient()
    try:
        holder = next(
            iter(client.list_lobbies(external_ref=body["external_ref"], active=True)),
            None,
        )
    except DotaLobbyError as exc:
        if exc.retryable and task.request.retries < task.max_retries:
            raise retry(_countdown(task.request.retries)) from exc
        internal_api.rejected(pk, code="conflict", detail=exc.detail, retryable=True)
        return "conflict"
    if holder is None:
        # It ended in between; the ref is free again.
        raise retry(CONFLICT_RETRY_SECONDS)
    answer = internal_api.conflict(pk, _view_json(holder)) or {}
    action = answer.get("action")
    if action == "adopt":
        if answer.get("close"):
            _close(client, pk, holder.id)
        return "adopted"
    if action == "close_and_retry":
        try:
            client.close_lobby(holder.id)
        except DotaLobbyError as exc:
            log.warning(
                "lobby_close_failed",
                lobby_id=holder.id,
                code=exc.code,
                **_LOG_TASKS,
            )
        if task.request.retries < task.max_retries:
            raise retry(CONFLICT_RETRY_SECONDS)
        return "conflict"
    return "conflict"


def _close_in_dota_lobby(
    client: DotaLobbyClient,
    pk: int,
    lobby_id: str,
    external_ref: str | None = None,
) -> str:
    """Close what dota_lobby holds for row `pk`, then report back.

    By lobby ID when the row has one. Otherwise by external_ref: only the
    active lobbies whose metadata names this row, so a replacement lobby for
    the same game is left alone. `not_found` and `invalid_state` (the match
    started after all) count as closed. Raises DotaLobbyError on anything
    else; the row then stays `close_pending` for the reconcile task.
    """
    if lobby_id:
        targets = [lobby_id]
    elif external_ref:
        targets = [
            view.id
            for view in client.list_lobbies(external_ref=external_ref, active=True)
            if view.metadata.get("game_lobby_id") == str(pk)
        ]
    else:
        targets = []
    outcome = "nothing_to_close"
    found = 0
    for target in targets:
        try:
            view = client.close_lobby(target)
        except DotaLobbyError as exc:
            if exc.code not in CLOSE_DONE_CODES:
                raise
            log.info(
                "lobby_close_not_needed",
                game_lobby_id=pk,
                lobby_id=target,
                code=exc.code,
                **_LOG_TASKS,
            )
            outcome = exc.code
            continue
        found += 1
        outcome = view.state
        internal_api.sync(pk, lobby=_view_json(view))
    answer = internal_api.close_done(pk, found=found)
    if answer and answer.get("close_pending"):
        # A create for this row may still land; reconcile looks again.
        return "waiting"
    return outcome


def _close(client: DotaLobbyClient, pk: int, lobby_id: str) -> None:
    try:
        _close_in_dota_lobby(client, pk, lobby_id)
    except DotaLobbyError as exc:
        log.warning(
            "lobby_close_failed",
            game_lobby_id=pk,
            lobby_id=lobby_id,
            code=exc.code,
            **_LOG_TASKS,
        )


@shared_task(bind=True, max_retries=3)
def close_dota_lobby(self: Task, game_lobby_id: int, lobby_id: str = "") -> str:
    """Close a lobby DraftForge no longer wants (DELETE is safe to repeat).

    Without `lobby_id` (the row ended before dota_lobby's answer was
    recorded) the row's external_ref is used. A close that does not get
    through stays pending on the row; the reconcile task tries again.
    """
    if not _enabled():
        return "disabled"
    external_ref = None
    if not lobby_id:
        row = internal_api.detail(game_lobby_id)
        if not row:
            return "unknown"
        lobby_id = row.get("lobby_id") or ""
        external_ref = row.get("external_ref")
    try:
        return _close_in_dota_lobby(
            DotaLobbyClient(), game_lobby_id, lobby_id, external_ref
        )
    except DotaLobbyError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(countdown=_countdown(self.request.retries)) from exc
        log.warning(
            "lobby_close_failed",
            game_lobby_id=game_lobby_id,
            lobby_id=lobby_id,
            code=exc.code,
            **_LOG_TASKS,
        )
        return exc.code


@shared_task(bind=True, max_retries=3)
def flip_lobby_sides(
    self: Task, game_lobby_id: int, lobby_id: str, radiant_team_ref: str
) -> str:
    """Swap sides so `radiant_team_ref` plays Radiant, unless it already does.

    Reads the lobby first, so a repeat never flips back.
    """
    if not _enabled():
        return "disabled"
    try:
        client = DotaLobbyClient()
        view = client.get_lobby(lobby_id)
        if view.teams.radiant.team_ref == radiant_team_ref:
            return "already"
        if view.teams.dire.team_ref != radiant_team_ref:
            return "unknown_team"
        if view.state not in ("waiting", "ready"):
            return "not_flippable"
        view = client.flip_teams(lobby_id)
    except DotaLobbyError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(countdown=_countdown(self.request.retries)) from exc
        # invalid_state: a flip is already on its way, or the lobby moved on.
        log.info(
            "lobby_flip_skipped",
            game_lobby_id=game_lobby_id,
            lobby_id=lobby_id,
            code=exc.code,
            **_LOG_TASKS,
        )
        return exc.code
    log.info(
        "lobby_sides_flipped",
        game_lobby_id=game_lobby_id,
        lobby_id=lobby_id,
        **_LOG_TASKS,
    )
    internal_api.sync(game_lobby_id, lobby=_view_json(view))
    return "flipped"


def _sync_one(
    client: DotaLobbyClient, row: dict[str, Any], view: LobbyView | None
) -> str:
    lobby_id = row["lobby_id"]
    if view is None:
        try:
            view = client.get_lobby(lobby_id)
        except DotaLobbyError as exc:
            if exc.code == "not_found":
                internal_api.sync(row["id"], missing=True)
                return "missing"
            raise
    events: list[dict[str, Any]] = []
    if view.seq > row["last_seq"]:
        events = [
            e.model_dump(mode="json")
            for e in client.list_events(lobby_id, after=row["last_seq"])
        ]
    internal_api.sync(row["id"], lobby=_view_json(view), events=events)
    return "events" if events else "synced"


@shared_task(bind=True, max_retries=3)
def backfill_lobby_events(self: Task, game_lobby_id: int) -> str:
    """Read the events after the last one applied (a webhook left a gap)."""
    if not _enabled():
        return "disabled"
    row = internal_api.detail(game_lobby_id)
    if not row or not row.get("lobby_id"):
        return "unknown"
    try:
        return _sync_one(DotaLobbyClient(), row, None)
    except DotaLobbyError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(countdown=_countdown(self.request.retries)) from exc
        log.warning(
            "lobby_backfill_failed",
            game_lobby_id=game_lobby_id,
            code=exc.code,
            **_LOG_TASKS,
        )
        return exc.code


@shared_task
def reconcile_dota_lobbies() -> dict[str, int] | str:
    """Beat task: bring every active lobby in line with dota_lobby."""
    if not _enabled():
        return "disabled"
    rows = internal_api.active()
    if rows is None:
        log.warning(
            "lobby_reconcile_skipped", reason="backend_unreachable", **_LOG_RECONCILE
        )
        return "backend_unreachable"
    counts = {
        "active": len(rows),
        "synced": 0,
        "events": 0,
        "missing": 0,
        "recreated": 0,
        "flips": 0,
        "errors": 0,
        "eligible": 0,
        "closes": 0,
    }
    try:
        client = DotaLobbyClient()
        listed: dict[str, LobbyView] = (
            {v.id: v for v in client.list_lobbies(active=True)}
            if any(r.get("lobby_id") for r in rows)
            else {}
        )
    except DotaLobbyError as exc:
        log.warning(
            "lobby_reconcile_skipped",
            reason=exc.code,
            retryable=exc.retryable,
            **_LOG_RECONCILE,
        )
        return exc.code

    for row in rows:
        if not row.get("lobby_id"):
            if row.get("resend_due"):
                create_dota_lobby.delay(
                    row["game_id"],
                    trigger=row.get("trigger") or "auto",
                    game_lobby_id=row["id"],
                )
                counts["recreated"] += 1
            continue
        try:
            outcome = _sync_one(client, row, listed.get(row["lobby_id"]))
        except DotaLobbyError as exc:
            counts["errors"] += 1
            log.warning(
                "lobby_reconcile_row_failed",
                game_lobby_id=row["id"],
                lobby_id=row["lobby_id"],
                code=exc.code,
                retryable=exc.retryable,
                **_LOG_RECONCILE,
            )
            continue
        counts["synced"] += 1
        if outcome in ("events", "missing"):
            counts[outcome] += 1
        if row.get("wants_flip") and row.get("dire_team_ref"):
            flip_lobby_sides.delay(row["id"], row["lobby_id"], row["dire_team_ref"])
            counts["flips"] += 1

    for row in internal_api.close_pending() or []:
        try:
            _close_in_dota_lobby(
                client, row["id"], row.get("lobby_id") or "", row["external_ref"]
            )
        except DotaLobbyError as exc:
            counts["errors"] += 1
            log.warning(
                "lobby_reconcile_close_failed",
                game_lobby_id=row["id"],
                lobby_id=row.get("lobby_id"),
                code=exc.code,
                retryable=exc.retryable,
                **_LOG_RECONCILE,
            )
            continue
        counts["closes"] += 1

    for game in internal_api.eligible_games() or []:
        create_dota_lobby.delay(game["id"], trigger="auto")
        counts["eligible"] += 1

    log.info("lobby_reconcile_summary", **counts, **_LOG_RECONCILE)
    return counts


@shared_task
def send_lobby_info(game_lobby_id: int) -> str:
    """DM rostered players the lobby name, password and their side (opt-in).

    The password is read from dota_lobby, so it is the one players need. It
    goes out in the DM only: no per-message log row stores the embed.
    """
    from app.internal_client import create_tournament_log, update_tournament_log
    from discordbot.utils import sync_send_dm
    from events.discord.tournament_embeds import build_lobby_info_embed

    if not _enabled():
        return "disabled"
    info = internal_api.notify_info(game_lobby_id)
    if not info:
        return "not_found"
    if not info.get("enabled"):
        return "Config disabled"
    if info.get("ended") or not info.get("lobby_id"):
        return "lobby_not_active"
    try:
        view = DotaLobbyClient().get_lobby(info["lobby_id"])
    except DotaLobbyError as exc:
        log.warning(
            "lobby_info_lookup_failed",
            game_lobby_id=game_lobby_id,
            code=exc.code,
            **_LOG_TASKS,
        )
        return exc.code
    password = view.password.get_secret_value() if view.password else ""
    recipients = info.get("recipients") or []
    matchup = f"{info.get('radiant_name')} vs {info.get('dire_name')}"

    log_resp = create_tournament_log(
        tournament_id=info["tournament_id"],
        category="notification",
        notification_type="lobby_info",
        message=f"Sending lobby info to {len(recipients)} players ({matchup})...",
        recipient_count=0,
        success=None,
    )
    tournament_log_id = log_resp.json().get("id") if log_resp and log_resp.ok else None

    sent = 0
    failed_users = []
    for person in recipients:
        embed = build_lobby_info_embed(
            info.get("tournament_name") or "",
            lobby_name=view.name or info.get("name") or "",
            password=password,
            side=person["side"],
            team_name=person["team_name"],
            matchup=matchup,
            region=info.get("region") or "",
        )
        # No tournament_log_id: the per-message log would store the embed,
        # and with it the password.
        if sync_send_dm(person["discord_id"], embed=embed):
            sent += 1
        else:
            failed_users.append(person.get("username") or person["discord_id"])

    message = f"Sent lobby info to {sent}/{len(recipients)} players ({matchup})"
    if failed_users:
        message += f". Failed: {', '.join(failed_users[:10])}"
    if tournament_log_id:
        update_tournament_log(
            tournament_log_id,
            recipient_count=sent,
            message=message,
            success=sent > 0,
        )
    log.info(
        "lobby_info_sent",
        game_lobby_id=game_lobby_id,
        tournament_id=info["tournament_id"],
        sent=sent,
        count=len(recipients),
        **_LOG_TASKS,
    )
    return message
