"""Tournaments: task config, participants, auto hero-draft games and hero-draft creation."""

from typing import TYPE_CHECKING

import requests

from app.internal_client import transport
from app.schemas import (
    AutoHeroDraftGameSchema,
    TournamentParticipantSchema,
    TournamentTaskSchema,
)

if TYPE_CHECKING:
    from app.schemas import (
        AutoHeroDraftGameSchema,
        TournamentParticipantSchema,
        TournamentTaskSchema,
    )


def get_tournament_for_task(pk: int) -> "TournamentTaskSchema | None":
    """Get tournament config for Celery tasks. Returns TournamentTaskData or None."""

    resp = transport.get(f"/tournaments/{pk}/full/")
    if resp and resp.ok:
        return TournamentTaskSchema.model_validate(resp.json())
    return None


def get_tournament_participants(
    tournament_id: int,
) -> list["TournamentParticipantSchema"]:
    """Get participants with Discord IDs. Returns list of TournamentParticipant."""

    resp = transport.get(f"/tournaments/{tournament_id}/participants/")
    if resp and resp.ok:
        return [TournamentParticipantSchema.model_validate(p) for p in resp.json()]
    return []


def get_match_participants(game_id: int) -> list["TournamentParticipantSchema"]:
    """Get match players with Discord IDs. Returns list of TournamentParticipant."""

    resp = transport.get(f"/games/{game_id}/participants/")
    if resp and resp.ok:
        return [TournamentParticipantSchema.model_validate(p) for p in resp.json()]
    return []


def get_auto_herodraft_games() -> list["AutoHeroDraftGameSchema"]:
    """Games ready for an auto-created hero draft. Returns list of AutoHeroDraftGame."""

    resp = transport.get("/tournaments/auto-herodraft-games/")
    if resp and resp.ok:
        return [AutoHeroDraftGameSchema.model_validate(g) for g in resp.json()]
    return []


def create_herodraft_for_game(game_id: int) -> requests.Response | None:
    """Atomically create a HeroDraft for a game. Returns response or None."""
    return transport.post(f"/games/{game_id}/create-herodraft/", {})
