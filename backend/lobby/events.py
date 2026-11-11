"""Apply dota_lobby events and lobby snapshots to GameLobby rows and games.

Webhook deliveries and the reconcile task both end up here. Events are stored
once by ID and applied strictly in `seq` order: an event that arrives ahead of
a missing one is stored and applied once the gap is filled (the caller then
fetches the missing events from dota_lobby).

Game effects, applied only by the game's active lobby while its teams still
match the game's (a lobby DraftForge already ended never touches the game):

- `match.started` moves a `pending` game to `live`. The match ID is kept on
  the GameLobby only: Game.gameid stays empty, so the Steam link (automatic or
  manual) still finds the game and sets its match ID and winner.
- `match.ended` is recorded on the GameLobby only (`provisional_*`). It never
  sets the winner, completes the game or advances the bracket: staff confirm
  the result, and the Steam league sync stays authoritative.
- A match that ends unscored (`scored: false`), or a lobby that ends after
  its match started without a scored result, moves the game from `live` back
  to `pending`, so organizers can request a new lobby.

Callers hold a row lock on the GameLobby (select_for_update) inside a
transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import Game
from lobby import broadcast, states
from lobby.models import GameLobby, GameLobbyEvent
from lobby.schemas import LobbyEvent, LobbyView
from lobby.services import game_teams, lobby_teams, match_abandoned, parse_team_ref
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "lobby", "subsystem": "events"}

# Events whose `reason` describes the lobby's state. On other events (a
# player kicked or unready, a failed launch) it is about the player or the
# launch, and must not become the lobby's state_reason.
STATE_REASON_EVENTS = frozenset(
    {
        "lobby.state_changed",
        "lobby.finished",
        "lobby.closed",
        "lobby.failed",
        "lobby.timed_out",
    }
)

PLAYER_STATUS_BY_EVENT = {
    "lobby.player_invited": "invited",
    "lobby.player_joined": "joined",
    "lobby.player_left": "left",
    "lobby.player_kicked": "kicked",
}


@dataclass
class IngestResult:
    stored: int = 0
    applied: int = 0
    duplicates: int = 0
    # True when an event is stored but cannot be applied yet: an earlier one
    # is missing.
    gap: bool = False
    game_changed: bool = False
    lobby_changed: bool = False
    applied_types: list[str] = field(default_factory=list)


def _set_state(game_lobby: GameLobby, state: str, reason: str | None = None) -> None:
    """Follow dota_lobby's state, but never revive a row DraftForge ended.

    A row ended locally (closed because the game's teams changed, or refused)
    only moves on to one of dota_lobby's terminal states.
    """
    if not state:
        return
    if game_lobby.ended and state not in states.SERVICE_TERMINAL_STATES:
        return
    if state not in GameLobby.State.values:
        log.warning("lobby_unknown_state", state=state, **_LOG)
        return
    if game_lobby.ended and game_lobby.state in states.SERVICE_TERMINAL_STATES:
        # Already ended in dota_lobby too; the first terminal state wins.
        return
    game_lobby.state = state
    if reason is not None:
        game_lobby.state_reason = (reason or "")[:64]


def _team_pk(game_lobby: GameLobby, ref: object) -> int | None:
    """A team ref of this lobby's game, as a Team pk."""
    pk = parse_team_ref(ref)
    if pk is None:
        return None
    game = game_lobby.game
    allowed = {
        game.radiant_team_id,
        game.dire_team_id,
        game_lobby.radiant_team_id,
        game_lobby.dire_team_id,
    }
    return pk if pk in allowed else None


def _set_sides(game_lobby: GameLobby, radiant_ref: object, dire_ref: object) -> None:
    radiant = _team_pk(game_lobby, radiant_ref)
    dire = _team_pk(game_lobby, dire_ref)
    if radiant is not None:
        game_lobby.radiant_team_id = radiant
    if dire is not None:
        game_lobby.dire_team_id = dire


def _player(game_lobby: GameLobby, account_id: object) -> dict[str, Any] | None:
    if not isinstance(account_id, int) or isinstance(account_id, bool):
        return None
    players = dict(game_lobby.players or {})
    entry = dict(players.get(str(account_id)) or {})
    players[str(account_id)] = entry
    game_lobby.players = players
    return entry


def _bind_summary(game_lobby: GameLobby, event: LobbyEvent) -> None:
    summary = event.lobby
    if not game_lobby.lobby_id:
        game_lobby.lobby_id = summary.id
        game_lobby.accepted_at = game_lobby.accepted_at or timezone.now()
    if summary.bot:
        game_lobby.bot = summary.bot[:64]
    if summary.gc_lobby_id:
        game_lobby.gc_lobby_id = summary.gc_lobby_id[:24]
    if summary.league_id:
        game_lobby.league_id = summary.league_id


def _owns_game(game_lobby: GameLobby, game: Game) -> bool:
    """Whether this lobby may change the game: it is the game's active lobby
    and was created for the teams the game has now.

    A row DraftForge ended (closed because the teams changed, or by staff)
    keeps receiving its lobby's events, but they no longer reach the game.
    """
    return not game_lobby.ended and lobby_teams(game_lobby) == game_teams(game)


def _apply_match_started(
    game_lobby: GameLobby, event: LobbyEvent, game: Game
) -> list[str]:
    """Store the match ID on the lobby; returns the Game fields changed."""
    data = event.data
    raw = data.get("match_id")
    try:
        match_id = int(str(raw))
    except (TypeError, ValueError):
        log.warning(
            "lobby_bad_match_id",
            event_id=event.id,
            lobby_id=game_lobby.lobby_id,
            **_LOG,
        )
        return []
    game_lobby.match_id = match_id
    game_lobby.match_started_at = event.occurred_at
    _set_sides(game_lobby, data.get("radiant_team_ref"), data.get("dire_team_ref"))

    if not _owns_game(game_lobby, game):
        log.info(
            "lobby_match_started_ignored",
            game_id=game.pk,
            game_lobby_id=game_lobby.pk,
            lobby_id=game_lobby.lobby_id,
            match_id=match_id,
            state_reason=game_lobby.state_reason,
            **_LOG,
        )
        return []
    if game.status == "pending":
        game.status = "live"
        return ["status"]
    return []


def release_game(game_lobby: GameLobby, game: Game) -> list[str]:
    """Move the game back to `pending` when its lobby's match was abandoned.

    Only a `live` game without a winner, whose live status this lobby set, is
    released, so a result staff or the Steam link recorded is never undone.
    The caller saves the game. Returns the Game fields changed.
    """
    if not match_abandoned(game_lobby) or not _owns_game(game_lobby, game):
        return []
    if game.status != "live" or game.winning_team_id is not None:
        return []
    if (
        GameLobby.objects.filter(game_id=game.pk, ended=False)
        .exclude(pk=game_lobby.pk)
        .exists()
    ):
        return []
    game.status = "pending"
    log.info(
        "lobby_match_abandoned",
        game_id=game.pk,
        game_lobby_id=game_lobby.pk,
        lobby_id=game_lobby.lobby_id,
        match_id=game_lobby.match_id,
        state=game_lobby.state,
        scored=game_lobby.provisional_scored,
        **_LOG,
    )
    return ["status"]


def _apply_match_ended(game_lobby: GameLobby, event: LobbyEvent) -> None:
    data = event.data
    raw = data.get("match_id")
    if raw is not None and game_lobby.match_id is None:
        try:
            game_lobby.match_id = int(str(raw))
        except (TypeError, ValueError):
            pass
    outcome = data.get("outcome")
    game_lobby.provisional_outcome = outcome if isinstance(outcome, int) else None
    game_lobby.provisional_outcome_name = str(data.get("outcome_name") or "")[:32]
    side = data.get("winner_side")
    game_lobby.provisional_winner_side = side if side in ("radiant", "dire") else ""
    game_lobby.provisional_winner_team_id = _team_pk(
        game_lobby, data.get("winner_team_ref")
    )
    scored = data.get("scored")
    game_lobby.provisional_scored = scored if isinstance(scored, bool) else None
    duration = data.get("duration_seconds")
    game_lobby.duration_seconds = duration if isinstance(duration, int) else None
    game_lobby.match_ended_at = event.occurred_at


def apply_event(game_lobby: GameLobby, event: LobbyEvent, game: Game) -> list[str]:
    """Apply one event to the row (and the game). Returns Game fields changed."""
    data = event.data
    kind = event.type
    _bind_summary(game_lobby, event)
    game_changed: list[str] = []

    if kind == "lobby.created":
        if data.get("gc_lobby_id"):
            game_lobby.gc_lobby_id = str(data["gc_lobby_id"])[:24]
        verified = data.get("league_verified")
        if isinstance(verified, bool):
            game_lobby.league_verified = verified
    elif kind == "lobby.create_failed":
        game_lobby.last_error_code = str(data.get("code") or "create_failed")[:48]
        game_lobby.last_error_detail = str(data.get("message") or "")
        game_lobby.last_error_at = event.occurred_at
    elif kind in ("lobby.teams_flipped", "lobby.roster_changed"):
        _set_sides(game_lobby, data.get("radiant_team_ref"), data.get("dire_team_ref"))
    elif kind in PLAYER_STATUS_BY_EVENT:
        entry = _player(game_lobby, data.get("account_id"))
        if entry is not None:
            entry["status"] = PLAYER_STATUS_BY_EVENT[kind]
            if kind == "lobby.player_invited":
                entry["invites_sent"] = data.get("invites_sent")
                entry["last_invite_at"] = event.occurred_at.isoformat()
            if kind in ("lobby.player_left", "lobby.player_kicked"):
                entry["seat"] = None
                entry["ready"] = False
    elif kind == "lobby.player_seated":
        entry = _player(game_lobby, data.get("account_id"))
        if entry is not None:
            entry["seat"] = data.get("seat")
    elif kind in ("lobby.player_ready", "lobby.player_unready"):
        entry = _player(game_lobby, data.get("account_id"))
        if entry is not None:
            entry["ready"] = kind == "lobby.player_ready"
    elif kind in ("lobby.launching", "lobby.launch_failed"):
        attempt = data.get("attempt")
        if isinstance(attempt, int):
            game_lobby.launch_attempts = max(game_lobby.launch_attempts, attempt)
        if kind == "lobby.launch_failed":
            game_lobby.last_error_code = "launch_failed"
            game_lobby.last_error_detail = str(data.get("reason") or "")
            game_lobby.last_error_at = event.occurred_at
    elif kind == "match.started":
        game_changed = _apply_match_started(game_lobby, event, game)
    elif kind == "match.ended":
        _apply_match_ended(game_lobby, event)

    reason = data.get("reason") if kind in STATE_REASON_EVENTS else None
    if kind == "lobby.state_changed":
        _set_state(game_lobby, str(data.get("to") or event.lobby.state), reason)
    else:
        _set_state(
            game_lobby,
            event.lobby.state,
            reason if isinstance(reason, str) else None,
        )
    return game_changed


def _store(game_lobby: GameLobby, event: LobbyEvent, raw: dict, source: str) -> bool:
    """Store the event once. False when it is already stored."""
    if GameLobbyEvent.objects.filter(event_id=event.id).exists():
        return False
    try:
        with transaction.atomic():
            GameLobbyEvent.objects.create(
                event_id=event.id,
                lobby=game_lobby,
                seq=event.seq,
                type=event.type[:40],
                occurred_at=event.occurred_at,
                payload=raw,
                source=source,
            )
    except IntegrityError:
        # Same seq under another ID: dota_lobby never sends that; keep the first.
        log.warning(
            "lobby_event_seq_clash",
            event_id=event.id,
            seq=event.seq,
            lobby_id=game_lobby.lobby_id,
            **_LOG,
        )
        return False
    return True


def ingest_events(
    game_lobby: GameLobby,
    events: Iterable[tuple[LobbyEvent, dict]],
    *,
    source: str,
) -> IngestResult:
    """Store events and apply every one that is next in sequence.

    `events` are (parsed, raw envelope) pairs. The caller holds the row lock.
    """
    result = IngestResult()
    for event, raw in sorted(events, key=lambda pair: pair[0].seq):
        if event.seq <= game_lobby.last_seq or not _store(
            game_lobby, event, raw, source
        ):
            result.duplicates += 1
            continue
        result.stored += 1

    game = Game.objects.select_for_update().get(pk=game_lobby.game_id)
    game_fields: set[str] = set()
    pending = {
        e.seq: e
        for e in GameLobbyEvent.objects.filter(
            lobby=game_lobby, applied_at__isnull=True, seq__gt=game_lobby.last_seq
        )
    }
    while game_lobby.last_seq + 1 in pending:
        stored = pending.pop(game_lobby.last_seq + 1)
        event = LobbyEvent.model_validate(stored.payload)
        game_fields.update(apply_event(game_lobby, event, game))
        stored.applied_at = timezone.now()
        stored.save(update_fields=["applied_at"])
        game_lobby.last_seq = stored.seq
        result.applied += 1
        result.applied_types.append(event.type)
        log.info(
            "lobby_event_applied",
            event_id=event.id,
            event_type=event.type,
            seq=event.seq,
            lobby_id=game_lobby.lobby_id,
            game_id=game.pk,
            source=source,
            **_LOG,
        )
    result.gap = bool(pending)
    if result.applied:
        game_fields.update(release_game(game_lobby, game))

    if result.applied:
        game_lobby.save()
        result.lobby_changed = True
    if game_fields:
        game.save(update_fields=sorted(game_fields))
        result.game_changed = True
    if result.applied:
        _after_change(game_lobby, game, result)
    return result


def apply_snapshot(game_lobby: GameLobby, view: LobbyView) -> bool:
    """Refresh the row from a LobbyView unless its events are ahead of it.

    Game effects come from events only, so a snapshot changes lobby fields:
    state, bot, sides, players. Returns True when it was applied.
    """
    if view.seq < game_lobby.last_seq:
        return False
    if not game_lobby.lobby_id:
        game_lobby.lobby_id = view.id
        game_lobby.accepted_at = game_lobby.accepted_at or timezone.now()
    _set_state(game_lobby, view.state, view.state_reason or "")
    game_lobby.bot = (view.bot or game_lobby.bot)[:64]
    game_lobby.gc_lobby_id = (view.gc_lobby_id or game_lobby.gc_lobby_id)[:24]
    if view.league_id:
        game_lobby.league_id = view.league_id
    if view.league_verified is not None:
        game_lobby.league_verified = view.league_verified
    _set_sides(game_lobby, view.teams.radiant.team_ref, view.teams.dire.team_ref)
    players: dict[str, Any] = {}
    for team in (view.teams.radiant, view.teams.dire):
        for p in team.players:
            players[str(p.account_id)] = {
                "status": p.status,
                "seat": p.seat,
                "ready": p.ready,
                "invites_sent": p.invites_sent,
                "last_invite_at": (
                    p.last_invite_at.isoformat() if p.last_invite_at else None
                ),
            }
    game_lobby.players = players
    game_lobby.pending_invites = list(view.pending_invites)
    game_lobby.launch_attempts = max(game_lobby.launch_attempts, view.launch_attempts)
    game_lobby.last_synced_at = timezone.now()
    game_lobby.save()
    return True


def _after_change(game_lobby: GameLobby, game: Game, result: IngestResult) -> None:
    """Cache invalidation, websocket messages and notifications, on commit."""
    if result.game_changed:
        tournament = game.tournament
        invalidate_after_commit(*(o for o in (game, tournament) if o is not None))
    broadcast.lobby_changed_on_commit(game_lobby, bracket_changed=result.game_changed)
    if "lobby.created" in result.applied_types:
        tournament = game.tournament
        if tournament is not None and tournament.discord_send_lobby_info:
            from lobby.tasks import send_lobby_info

            pk = game_lobby.pk
            transaction.on_commit(lambda: send_lobby_info.delay(pk))
