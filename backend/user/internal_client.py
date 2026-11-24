"""Users: avatar checks and updates, batched avatar refresh and Discord name sync."""

from typing import Any

import requests

from app.internal_client import transport
from telemetry.logging import get_logger

logger = get_logger(__name__)


# ---- Avatars ----


def get_users_for_avatar_check(
    has_avatar: bool | None = None, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Get users with Discord IDs for avatar validation.

    Returns list of dicts with pk, discord_id, avatar, username.
    """
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if has_avatar is not None:
        params["has_avatar"] = "true" if has_avatar else "false"
    resp = transport.get("/users/avatar-check/", params=params)
    if resp and resp.ok:
        return resp.json()
    return []


def update_user_avatar(pk: int, avatar: str | None) -> requests.Response | None:
    """Update CustomUser avatar hash."""
    return transport.patch(f"/users/{pk}/avatar/", {"avatar": avatar})


# ---- Batched avatar refresh (used by user/tasks/avatar_refresh.py) ----


def list_discord_linked_users() -> list[dict[str, Any]]:
    """Return every Discord-linked user as a flat list, or [] on failure.

    Each entry: {pk, discord_id, avatar, username}.

    A genuinely empty list and a network failure both return [] — the
    caller's "nothing to do" branch handles both. transport.get has
    already logged the network failure with the full path/status,
    so we don't double-log here.
    """
    resp = transport.get("/users/discord-linked/")
    if resp is None or not resp.ok:
        return []
    try:
        return resp.json()
    except ValueError:
        logger.error(
            "discord_linked_users_invalid_json",
            system="internal_client",
            subsystem="http",
            body_excerpt=resp.text[:200],
        )
        return []


def list_discord_guild_ids() -> list[str]:
    """Return distinct Org discord_server_ids, or [] on failure.

    See list_discord_linked_users for the empty-vs-failure semantics.
    """
    resp = transport.get("/orgs/discord-guild-ids/")
    if resp is None or not resp.ok:
        return []
    try:
        return resp.json().get("guild_ids", [])
    except ValueError:
        logger.error(
            "discord_guild_ids_invalid_json",
            system="internal_client",
            subsystem="http",
            body_excerpt=resp.text[:200],
        )
        return []


def bulk_update_user_avatars(updates: list[dict[str, Any]]) -> int:
    """Bulk-update avatar hashes. `updates`: list of {pk, avatar}.

    Returns updated count (0 on empty or network failure).
    """
    if not updates:
        return 0
    resp = transport.post("/users/avatars/bulk-update/", {"updates": updates})
    if resp is None or not resp.ok:
        return 0
    try:
        return int(resp.json().get("updated", 0))
    except (ValueError, TypeError):
        return 0


# ---- Discord name sync (used by user/tasks/discord_name_sync.py) ----


def list_discord_name_sync_targets(
    *, scope: str = "active", org_id: int | None = None, lock: bool = True
) -> list[dict]:
    params: dict[str, object] = {"scope": scope}
    if org_id is not None:
        params["org_id"] = org_id
    if lock:
        params["lock"] = 1
    resp = transport.get("/orgs/discord-name-sync-targets/", params=params)
    if resp is None or not resp.ok:
        return []
    try:
        return resp.json()
    except ValueError:
        logger.error(
            "discord_name_sync_targets_invalid_json",
            system="internal_client",
            subsystem="http",
            body_excerpt=resp.text[:200],
        )
        return []


def bulk_update_member_names(
    guild_id: str,
    org_ids: list[int],
    members: list[dict],
    *,
    complete: bool,
    fetched_at: float | None,
) -> dict | None:
    resp = transport.post(
        "/discord/member-names/bulk-update/",
        {
            "guild_id": guild_id,
            "org_ids": org_ids,
            "complete": complete,
            "fetched_at": fetched_at,
            "members": members,
        },
    )
    if resp is None or not resp.ok:
        return None
    try:
        return resp.json()
    except ValueError:
        logger.error(
            "discord_member_names_bulk_update_invalid_json",
            system="internal_client",
            subsystem="http",
            body_excerpt=resp.text[:200],
        )
        return None
