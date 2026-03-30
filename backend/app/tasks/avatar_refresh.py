"""Celery tasks for Discord avatar refresh.

Uses internal API for all database access. Discord CDN/API calls
are made directly from the worker since they're external HTTP calls.
"""

import logging

import requests
from celery import shared_task
from django.conf import settings

from app.internal_client import get_users_for_avatar_check, update_user_avatar

log = logging.getLogger(__name__)


def _is_test_environment():
    """Check if running in test environment (skip Discord API calls)."""
    return getattr(settings, "TEST", False) and settings.DEBUG


def _is_avatar_url_valid(url):
    """Check if the avatar URL returns a valid response (not 404)."""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _fetch_discord_avatar(discord_id):
    """Fetch latest avatar hash from Discord API. Returns hash or None."""
    token = getattr(settings, "DISCORD_BOT_TOKEN", None)
    if not token:
        return None
    try:
        resp = requests.get(
            f"{settings.DISCORD_API_BASE_URL}/users/{discord_id}",
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
