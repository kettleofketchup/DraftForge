"""Celery tasks for Discord avatar refresh.

Uses internal API for all database access. Discord CDN/API calls
are made directly from the worker since they're external HTTP calls.
"""

import asyncio
import logging
import os
from typing import Any

import httpx
import requests
from celery import shared_task

from app.internal_client import get_users_for_avatar_check, update_user_avatar

log = logging.getLogger(__name__)

# Stagger between Discord API calls to stay well under the bot global rate
# limit (50 req/s) and avoid burst-induced 429s on shared infra.
_DISCORD_STAGGER_S = 0.2

# Page size for `GET /guilds/{id}/members` (Discord max).
_GUILD_MEMBER_LIMIT = 1000

# Soft cap on paginated calls per guild so a buggy / runaway response can't
# loop forever. 50 pages × 1000 = 50k members per guild — far above any
# realistic DraftForge org. If this cap is hit, the task logs a warning and
# falls through; missed users get refreshed on the next scheduled run.
_GUILD_MEMBER_MAX_PAGES = 50


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


async def _fetch_guild_members(
    client: httpx.AsyncClient,
    guild_id: str,
    token: str,
    api_base: str,
    needed_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Page through `GET /guilds/{id}/members` until the guild is exhausted
    or we've matched every local user we need for this guild.

    Pagination is sequential because each page's `after` cursor is the last
    member id of the previous page. Pages within a guild can't be made
    concurrent. Sequential paging stops as soon as either:

      a) The response contains fewer than `_GUILD_MEMBER_LIMIT` members
         (last page reached).
      b) `needed_ids` is provided and every id in it has been seen — we
         don't need to keep paging through members we don't care about.
      c) We hit `_GUILD_MEMBER_MAX_PAGES` (soft cap; logs a warning).

    Returns the accumulated member objects (each contains a `.user` with
    `.id` and `.avatar`).
    """
    headers = {"Authorization": f"Bot {token}"}
    members: list[dict[str, Any]] = []
    seen_needed: set[str] = set()
    after = "0"
    pages_done = 0
    for page in range(_GUILD_MEMBER_MAX_PAGES):
        try:
            resp = await client.get(
                f"{api_base}/guilds/{guild_id}/members",
                headers=headers,
                params={"limit": _GUILD_MEMBER_LIMIT, "after": after},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            log.warning(
                "guild members fetch failed",
                extra={"guild_id": guild_id, "page": page, "error": str(exc)},
            )
            break
        if resp.status_code != 200:
            log.warning(
                "guild members non-200",
                extra={
                    "guild_id": guild_id,
                    "page": page,
                    "status": resp.status_code,
                },
            )
            break
        page_members = resp.json()
        if not isinstance(page_members, list) or not page_members:
            break
        members.extend(page_members)
        pages_done = page + 1
        # Early exit: if all the local users we care about have been seen,
        # there's nothing to gain from paging further through the guild.
        if needed_ids is not None:
            for m in page_members:
                uid = (m.get("user") or {}).get("id")
                if uid and str(uid) in needed_ids:
                    seen_needed.add(str(uid))
            if needed_ids and seen_needed >= needed_ids:
                break
        if len(page_members) < _GUILD_MEMBER_LIMIT:
            break
        last = page_members[-1].get("user", {}).get("id")
        if not last:
            break
        after = str(last)
        await asyncio.sleep(_DISCORD_STAGGER_S)
    if pages_done >= _GUILD_MEMBER_MAX_PAGES:
        log.warning(
            "guild member pagination hit soft cap",
            extra={
                "guild_id": guild_id,
                "pages": pages_done,
                "members_fetched": len(members),
                "needed": len(needed_ids) if needed_ids else None,
                "matched": len(seen_needed),
            },
        )
    return members


async def _build_avatar_map(
    guild_ids: list[str],
    needed_ids: set[str],
) -> dict[str, str | None]:
    """Concurrently fetch members for each guild and aggregate
    `discord_id -> avatar_hash` mappings. Guilds run in parallel; pages
    within a guild run sequentially (cursor dependency).

    `needed_ids` is the set of local users' Discord ids we care about — each
    guild stops paging early once it has surfaced every id in this set, so
    huge guilds don't force a full member walk for a handful of local users.
    """
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        return {}
    api_base = os.environ.get("DISCORD_API_BASE_URL", "https://discord.com/api/v10")
    avatar_map: dict[str, str | None] = {}
    async with httpx.AsyncClient() as client:

        async def _stagger_then_fetch(idx: int, guild_id: str):
            # Stagger inter-guild dispatches to spread the initial burst.
            await asyncio.sleep(idx * _DISCORD_STAGGER_S)
            return await _fetch_guild_members(
                client, guild_id, token, api_base, needed_ids=needed_ids
            )

        tasks = [_stagger_then_fetch(i, gid) for i, gid in enumerate(guild_ids)]
        for guild_members in await asyncio.gather(*tasks):
            for member in guild_members:
                user_obj = member.get("user") or {}
                discord_id = user_obj.get("id")
                if discord_id:
                    avatar_map[str(discord_id)] = user_obj.get("avatar")
    return avatar_map


@shared_task
def refresh_avatars_batched():
    """Bulk avatar refresh via Discord guild-members API.

    Replaces the per-user `/users/{id}` fan-out (one synchronous outbound
    call per local user, blocked Daphne for 27s during the test suite) with:

      1. Skip users that have no `discordId` (most "Failed to fetch" log
         lines were coming from non-Discord-linked test users).
      2. Group orgs by `discord_server_id`, then for each guild fetch its
         members in 1–3 paginated calls (`limit=1000`), staggered to
         respect Discord's global rate limit.
      3. Build `discord_id -> avatar_hash` map, bulk-update local users
         where the hash changed.
      4. Run via `asyncio` + `httpx.AsyncClient` so multiple guilds fetch
         concurrently in the worker process (Daphne is unaffected).

    This task is idempotent and rate-limited at the calling endpoint
    (`/api/avatars/refresh/`) via a 1-hour cache key set BEFORE dispatch.
    """
    if _is_test_environment():
        log.info("Skipping batched avatar refresh in test environment")
        return {"checked": 0, "updated": 0, "skipped": True}

    # Lazy imports keep the module importable in worker startup paths that
    # haven't fully bootstrapped Django.
    from app.models import CustomUser, Organization

    # Discordful users only — non-Discord-linked accounts can't gain or lose
    # a Discord avatar.
    candidate_users = list(
        CustomUser.objects.filter(discordId__isnull=False)
        .exclude(discordId="")
        .values("pk", "discordId", "avatar", "username")
    )
    if not candidate_users:
        log.info("No Discord-linked users to refresh")
        return {"checked": 0, "updated": 0}

    guild_ids = list(
        Organization.objects.filter(discord_server_id__isnull=False)
        .exclude(discord_server_id="")
        .values_list("discord_server_id", flat=True)
        .distinct()
    )
    if not guild_ids:
        log.info("No orgs with discord_server_id; nothing to refresh")
        return {"checked": len(candidate_users), "updated": 0}

    log.info(
        "Refreshing avatars: %d users across %d guilds",
        len(candidate_users),
        len(guild_ids),
    )
    needed_ids = {str(u["discordId"]) for u in candidate_users}
    avatar_map = asyncio.run(_build_avatar_map(guild_ids, needed_ids))

    updated = 0
    for u in candidate_users:
        discord_id = str(u["discordId"])
        if discord_id not in avatar_map:
            continue
        new_avatar = avatar_map[discord_id]
        if new_avatar == u["avatar"]:
            continue
        # Use update() to skip save() signals + invalidate cacheops in a
        # single statement; bulk path can revisit per-pk if invalidation
        # becomes important.
        CustomUser.objects.filter(pk=u["pk"]).update(avatar=new_avatar)
        updated += 1

    log.info(
        "Batched avatar refresh complete: checked=%d, updated=%d, guilds=%d",
        len(candidate_users),
        updated,
        len(guild_ids),
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
