"""Pydantic schemas for internal API data transfer.

These schemas serve as the contract between Django (producer) and
celery workers (consumer). They validate at both ends:

Django side (serializer):
    EventTaskData.model_validate(EventSerializer(event).data)
    → catches if serializer output drifts from schema

Celery side (consumer):
    event = EventTaskData(**api_response)
    → catches if API response drifts from what celery expects

When Django model fields change, update BOTH the serializer AND this
schema. The Pydantic ValidationError will catch any mismatch immediately.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.display_names import first_name


class TournamentUserSchema(BaseModel):
    """Validates: TournamentUserSerializer (app/serializers.py)"""

    pk: int
    username: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    discordId: Optional[str] = None
    discordNickname: Optional[str] = None
    guildNickname: Optional[str] = None
    steam_account_id: Optional[int] = None
    avatarUrl: Optional[str] = None
    mmr: Optional[int] = None
    mmr_game_type: int | None = None
    league_mmr: Optional[int] = None

    @property
    def display_name(self) -> str:
        return (
            first_name(
                self.guildNickname, self.discordNickname, self.nickname, self.username
            )
            or f"User {self.pk}"
        )

    model_config = {"extra": "ignore"}


class TournamentParticipantSchema(BaseModel):
    """Validates: get_tournament_participants() (app/views/internal.py)"""

    user_pk: int
    discord_id: str
    username: str = ""
    model_config = {"extra": "ignore"}


class TournamentTaskSchema(BaseModel):
    """Validates: get_tournament_for_task() (app/views/internal.py)"""

    id: int
    name: str
    state: str
    date_played: Optional[datetime] = None
    auto_create_hero_drafts: bool = False
    discord_send_draft_link: bool = False
    discord_send_herodraft_link: bool = False
    tournament_type: str = "double_elimination"
    draft_type: str = "shuffle"

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
