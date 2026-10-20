"""Shared steam_account_id collision helpers.

CustomUser.steam_account_id is unique=True, so every write path needs the
same "who already holds this?" question answered the same way. Used by the
org-scoped update view and the lookup endpoint the edit form calls on blur;
the global endpoint is covered by a UniqueValidator on UserSerializer
instead.
"""

from __future__ import annotations

from typing import Any

from app.models import CustomUser


def steam_account_id_holder(
    steam_account_id: int | None, *, exclude_pk: int | None = None
) -> CustomUser | None:
    """Return the user already holding this Friend ID, or None if it is free."""
    if steam_account_id is None:
        return None
    qs = CustomUser.objects.filter(steam_account_id=steam_account_id)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def steam_account_id_identity(user: CustomUser) -> dict[str, Any]:
    """Identify a Friend ID holder for display.

    nickname/username only — the same fields GET /api/users/ already exposes
    to any authenticated user.
    """
    return {
        "pk": user.pk,
        "nickname": user.nickname or "",
        "username": user.username,
    }


def steam_account_id_conflict_payload(
    steam_account_id: int, holder: CustomUser
) -> dict[str, Any]:
    """Body for a 409, carrying enough for the UI to name the holder."""
    identity = steam_account_id_identity(holder)
    label = identity["nickname"] or identity["username"]
    return {
        "code": "steam_account_id_taken",
        "error": (
            f"Friend ID {steam_account_id} is already assigned to "
            f"{label} (@{identity['username']})."
        ),
        "conflict": identity,
    }
