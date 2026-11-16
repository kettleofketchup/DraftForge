from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import CustomUser


def first_name(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if candidate and (stripped := candidate.strip()):
            return stripped
    return None


def user_display_name(user: CustomUser, *, guild_nickname: str | None = None) -> str:
    return (
        first_name(guild_nickname, user.discordNickname, user.username)
        or f"User {user.pk}"
    )
