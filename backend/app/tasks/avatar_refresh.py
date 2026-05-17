"""Celery tasks for Discord avatar refresh.

Uses internal API for all database access. Discord CDN/API calls
are made directly from the worker since they're external HTTP calls.
"""

import logging
import os

import requests
from celery import shared_task

from app.internal_client import get_users_for_avatar_check, update_user_avatar
from telemetry.logging import get_logger

# Stdlib `log` is retained for the older per-user tasks in this file that
# still use printf-style formatting. New code uses `slog` — the project's
# standard structlog BoundLogger with system/subsystem kwargs.
log = logging.getLogger(__name__)
slog = get_logger(__name__)


def _is_test_environment():
    """Check if running in test environment (skip Discord API calls)."""
    return os.environ.get("TEST", "").lower() == "true" and os.environ.get("DEBUG", "").lower() == "true"


def _is_avatar_url_valid(url):
    """Check if the avatar URL returns a valid response (not 404)."""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _fetch_discord_avatar(discord_id):
    """Fetch latest avatar hash from Discord API. Returns hash or None."""
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        return None
    api_base = os.environ.get("DISCORD_API_BASE_URL", "https://discord.com/api/v10")
    try:
        resp = requests.get(
            f"{api_base}/users/{discord_id}",
            headers={"Authorization": f"Bot {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("avatar")
    except requests.RequestException as e:
        log.error(f"Discord API error for {discord_id}: {e}")
    return None


def _check_and_update_user(user):
    """Check a single user's avatar and update via internal API if needed.

    Returns True if avatar was updated.
    """
    discord_id = user["discord_id"]
    current_avatar = user["avatar"]
    pk = user["pk"]

    if current_avatar:
        extension = "gif" if current_avatar.startswith("a_") else "png"
        url = f"https://cdn.discordapp.com/avatars/{discord_id}/{current_avatar}.{extension}"
        if _is_avatar_url_valid(url):
            return False

    # Avatar missing or invalid — fetch from Discord
    new_avatar = _fetch_discord_avatar(discord_id)
    if new_avatar is None:
        return False
    if new_avatar == current_avatar:
        return False

    resp = update_user_avatar(pk, new_avatar)
    if resp and resp.ok:
        log.info(f"Updated avatar for user {user['username']} (pk={pk})")
        return True

    log.error(f"Failed to update avatar for user {user['username']} (pk={pk})")
    return False


@shared_task
def refresh_discord_avatars(batch_size: int = 100):
    """Refresh Discord avatars for users with existing avatars.

    Checks avatar URLs and updates them if they've changed or become invalid.
    Runs periodically via Celery Beat.
    """
    if _is_test_environment():
        log.info("Skipping Discord avatar refresh in test environment")
        return {"checked": 0, "updated": 0, "failed": 0, "skipped": True}

    log.info(f"Starting Discord avatar refresh (batch_size={batch_size})")

    users = get_users_for_avatar_check(has_avatar=True, limit=batch_size)
    checked = 0
    updated = 0
    failed = 0

    for user in users:
        try:
            checked += 1
            if _check_and_update_user(user):
                updated += 1
        except Exception as e:
            failed += 1
            log.error(f"Error refreshing avatar for user {user['username']}: {e}")

    log.info(
        f"Avatar refresh complete: checked={checked}, updated={updated}, failed={failed}"
    )
    return {"checked": checked, "updated": updated, "failed": failed}


@shared_task
def refresh_single_user_avatar(user_id: int):
    """Refresh Discord avatar for a specific user."""
    if _is_test_environment():
        return {"updated": False, "skipped": True}

    # Fetch this single user's data
    users = get_users_for_avatar_check(limit=1000)
    user = next((u for u in users if u["pk"] == user_id), None)
    if not user:
        return {"updated": False, "error": "User not found or has no Discord ID"}

    try:
        updated = _check_and_update_user(user)
        return {"updated": updated}
    except Exception as e:
        return {"updated": False, "error": str(e)}


@shared_task
def refresh_avatars_batched():
    """Bulk avatar refresh via Discord guild-members API.

    Replaces the per-user `/users/{id}` fan-out (one synchronous outbound
    call per local user, blocked Daphne for 27s during the test suite) with:

      1. Skip users that have no `discordId` (most "Failed to fetch" log
         lines were coming from non-Discord-linked test users).
      2. Group orgs by `discord_server_id`, then for each guild call
         `discordbot.services.users.get_discord_members_data(guild_id)`.
         That helper paginates `GET /guilds/{id}/members?limit=1000` until
         exhausted AND caches the full member list per guild under the
         Redis key `discord_members_{guild_id}` (15s TTL). Reusing it
         means:
           - cache hit when search-members or refresh-members has run in
             the last 15 seconds → avatar refresh becomes free in that
             window (no Discord call at all).
           - single source of truth for pagination + rate-limit handling.
           - any future improvements to the helper (e.g. retry on 429)
             benefit avatar refresh automatically.
      3. Build `discord_id -> avatar_hash` map across guilds, post the
         changed rows in a single bulk-update call to
         `/api/internal/users/avatars/bulk-update/` — the backend does
         `CustomUser.objects.bulk_update(...)` + `invalidate_model` in
         one round-trip. Workers do not touch the ORM.

    This task is idempotent and rate-limited at the calling endpoint
    (`/api/avatars/refresh/`) via a 1-hour cache key set BEFORE dispatch.
    """
    if _is_test_environment():
        slog.info(
            "avatars_refresh_skipped",
            system="avatars",
            subsystem="refresh",
            reason="test_environment",
        )
        return {"checked": 0, "updated": 0, "skipped": True}

    # Lazy imports keep the module importable in worker startup paths that
    # haven't fully bootstrapped Django.
    from app.internal_client import (
        bulk_update_user_avatars,
        list_discord_guild_ids,
        list_discord_linked_users,
    )
    from discordbot.services.users import get_discord_members_data

    # Discordful users only — non-Discord-linked accounts can't gain or lose
    # a Discord avatar. Empty list here means either no Discord-linked users
    # OR the internal endpoint was unreachable; _get already logs the latter.
    candidate_users = list_discord_linked_users()
    if not candidate_users:
        slog.info(
            "avatars_refresh_skipped",
            system="avatars",
            subsystem="refresh",
            reason="no_discord_linked_users_or_backend_down",
        )
        return {"checked": 0, "updated": 0}

    guild_ids = list_discord_guild_ids()
    if not guild_ids:
        slog.info(
            "avatars_refresh_skipped",
            system="avatars",
            subsystem="refresh",
            reason="no_org_guilds_or_backend_down",
            candidate_user_count=len(candidate_users),
        )
        return {"checked": len(candidate_users), "updated": 0}

    slog.info(
        "avatars_refresh_started",
        system="avatars",
        subsystem="refresh",
        candidate_user_count=len(candidate_users),
        guild_count=len(guild_ids),
    )

    # Build discord_id → avatar_hash across all guilds. The shared helper
    # already paginates each guild fully and caches the result per-guild;
    # we just consume the cached/fresh member lists here.
    avatar_map: dict[str, str | None] = {}
    guilds_failed = 0
    for guild_id in guild_ids:
        try:
            members = get_discord_members_data(guild_id=guild_id)
        except Exception as exc:
            guilds_failed += 1
            slog.warning(
                "avatars_guild_fetch_failed",
                system="avatars",
                subsystem="refresh",
                guild_id=guild_id,
                error=str(exc),
            )
            continue
        for member in members:
            user_obj = (member or {}).get("user") or {}
            discord_id = user_obj.get("id")
            if discord_id:
                avatar_map[str(discord_id)] = user_obj.get("avatar")

    # Collect changed rows and bulk-update in one shot via the internal
    # endpoint. Per-row PATCH was O(N) round-trips; at 100k users with
    # ~5% churn that's 5,000 calls (~150s in a worker). The bulk endpoint
    # batches all changed rows into one POST → one bulk_update on the
    # backend, batched server-side at 500 rows per CASE/WHEN UPDATE.
    updates = []
    for u in candidate_users:
        discord_id = str(u["discord_id"])
        if discord_id not in avatar_map:
            continue
        new_avatar = avatar_map[discord_id]
        if new_avatar == u["avatar"]:
            continue
        updates.append({"pk": u["pk"], "avatar": new_avatar})

    updated = bulk_update_user_avatars(updates) if updates else 0

    slog.info(
        "avatars_refresh_complete",
        system="avatars",
        subsystem="refresh",
        checked=len(candidate_users),
        updated=updated,
        guild_count=len(guild_ids),
        guilds_failed=guilds_failed,
    )
    return {
        "checked": len(candidate_users),
        "updated": updated,
        "guilds": len(guild_ids),
    }


@shared_task
def refresh_all_discord_data():
    """Refresh all Discord data for users (avatars, usernames, etc.).

    Iterates through all users with Discord IDs in batches.
    """
    if _is_test_environment():
        log.info("Skipping full Discord data refresh in test environment")
        return {"checked": 0, "updated": 0, "failed": 0, "skipped": True}

    batch_size = 50
    total_checked = 0
    total_updated = 0
    total_failed = 0

    log.info("Starting full Discord data refresh")

    # Fetch all users once, paginated
    offset = 0
    all_users = []
    while True:
        batch = get_users_for_avatar_check(limit=batch_size, offset=offset)
        if not batch:
            break
        all_users.extend(batch)
        offset += batch_size

    log.info(f"Found {len(all_users)} users with Discord IDs")

    for user in all_users:
        try:
            total_checked += 1
            if _check_and_update_user(user):
                total_updated += 1
        except Exception as e:
            total_failed += 1
            log.error(f"Error refreshing Discord data for user {user['username']}: {e}")

        if total_checked % 50 == 0:
            log.debug(f"Processed {total_checked}/{len(all_users)} users")

    log.info(
        f"Full Discord refresh complete: checked={total_checked}, "
        f"updated={total_updated}, failed={total_failed}"
    )
    return {
        "checked": total_checked,
        "updated": total_updated,
        "failed": total_failed,
    }
