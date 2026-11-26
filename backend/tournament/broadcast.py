"""Tell a tournament's open pages that its data changed.

Sends to the `tournament_<id>` group TournamentConsumer serves, after the
write commits so cacheops has already evicted what the clients refetch:

- `bracket.update` when games changed (results, slots, links, hero drafts).
- `tournament.update` for everything else, with the kind of change.

Payloads carry ids only; clients refetch. A missing or failing channel layer
is logged, never raised.
"""

from __future__ import annotations

from typing import Literal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from telemetry.logging import get_logger

log = get_logger(__name__)

TournamentChange = Literal["team", "members", "settings", "placement"]


def send(tournament_id: int, message: dict[str, object]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "tournament_broadcast_skipped",
            system="tournament",
            subsystem="broadcast",
            reason="no_channel_layer",
            tournament_id=tournament_id,
        )
        return
    try:
        async_to_sync(channel_layer.group_send)(f"tournament_{tournament_id}", message)
    except Exception as exc:  # noqa: BLE001 - the write already committed
        log.warning(
            "tournament_broadcast_failed",
            system="tournament",
            subsystem="broadcast",
            tournament_id=tournament_id,
            message_type=message.get("type"),
            error=str(exc),
        )


def send_tournament_update(
    tournament_id: int | None, kind: TournamentChange, *, team_id: int | None = None
) -> None:
    if tournament_id is None:
        return
    send(tournament_id, {"type": "tournament.update", "kind": kind, "team_id": team_id})


def bracket_changed_on_commit(
    tournament_id: int | None, game_id: int | None = None
) -> None:
    if tournament_id is None:
        return
    message: dict[str, object] = {"type": "bracket.update", "game_id": game_id}
    transaction.on_commit(lambda: send(tournament_id, message))


def tournament_changed_on_commit(
    tournament_id: int | None, kind: TournamentChange, *, team_id: int | None = None
) -> None:
    if tournament_id is None:
        return
    transaction.on_commit(
        lambda: send_tournament_update(tournament_id, kind, team_id=team_id)
    )
