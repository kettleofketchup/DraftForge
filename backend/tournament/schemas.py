"""Pydantic schemas for the tournament internal API.

The Django side validates the internal tournament views against them and the
celery side (``tournament.internal_client``) parses the responses with them.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TournamentParticipantSchema(BaseModel):
    """Validates: get_tournament_participants() (tournament/views/internal.py)"""

    user_pk: int
    discord_id: str
    username: str = ""
    model_config = {"extra": "ignore"}


class TournamentTaskSchema(BaseModel):
    """Validates: get_tournament_for_task() (tournament/views/internal.py)"""

    id: int
    name: str
    state: str
    date_played: datetime | None = None
    auto_create_hero_drafts: bool = False
    discord_send_draft_link: bool = False
    discord_send_herodraft_link: bool = False
    tournament_type: str = "double_elimination"
    draft_type: str = "shuffle"
    organization_id: int | None = None

    @property
    def pk(self) -> int:
        return self.id

    model_config = {"extra": "ignore"}


class GameWithoutHeroDraftSchema(BaseModel):
    """A game with both teams assigned and no hero draft yet."""

    id: int
    radiant_team_id: int
    radiant_team_name: str = ""
    dire_team_id: int
    dire_team_name: str = ""
    round: int = 1
    has_captains: bool = False
    model_config = {"extra": "ignore"}


class AutoHeroDraftGameSchema(GameWithoutHeroDraftSchema):
    """Validates: list_auto_herodraft_games() (draft/views/hero_internal.py)"""

    tournament_id: int
    discord_send_herodraft_link: bool = False
