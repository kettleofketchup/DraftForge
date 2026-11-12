"""Tell a tournament's websocket clients that a game's lobby changed.

Sends to the `tournament_<id>` group TournamentConsumer serves:

- `lobby_event` with the game's lobby state, match ID and provisional winner
  side. Never the password.
- `bracket_update` when the game itself changed (gameid or status), which the
  frontend already answers by refetching the bracket.

Messages go out after the transaction commits, and a missing or failing
channel layer is logged, never raised.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from lobby.models import GameLobby
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "lobby", "subsystem": "broadcast"}


def lobby_message(game_lobby: GameLobby) -> dict[str, object]:
    return {
        "type": "lobby.event",
        "game_id": game_lobby.game_id,
        "game_lobby_id": game_lobby.pk,
        "state": game_lobby.state,
        "match_id": str(game_lobby.match_id) if game_lobby.match_id else None,
        "provisional_winner_side": game_lobby.provisional_winner_side or None,
    }


def send(tournament_id: int, messages: list[dict[str, object]]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "lobby_broadcast_skipped",
            reason="no_channel_layer",
            tournament_id=tournament_id,
            **_LOG,
        )
        return
    group = f"tournament_{tournament_id}"
    for message in messages:
        try:
            async_to_sync(channel_layer.group_send)(group, message)
        except Exception as exc:  # noqa: BLE001 - never break the caller
            log.warning(
                "lobby_broadcast_failed",
                tournament_id=tournament_id,
                message_type=message.get("type"),
                error=str(exc),
                **_LOG,
            )


def lobby_changed_on_commit(game_lobby: GameLobby, *, bracket_changed: bool) -> None:
    tournament_id = game_lobby.game.tournament_id
    if tournament_id is None:
        return
    messages = [lobby_message(game_lobby)]
    if bracket_changed:
        messages.append({"type": "bracket.update", "game_id": game_lobby.game_id})
    transaction.on_commit(lambda: send(tournament_id, messages))
