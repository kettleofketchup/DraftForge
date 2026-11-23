"""Pydantic schemas for internal API data transfer.

These schemas serve as the contract between Django (producer) and
celery workers (consumer). They validate at both ends:

Django side (serializer):
    TournamentUserSchema.model_validate(TournamentUserSerializer(user).data)
    → catches if serializer output drifts from schema

Celery side (consumer):
    user = TournamentUserSchema(**api_response)
    → catches if API response drifts from what celery expects

When Django model fields change, update BOTH the serializer AND this
schema. The Pydantic ValidationError will catch any mismatch immediately.
"""

from __future__ import annotations

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
