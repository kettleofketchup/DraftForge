"""Celery tasks for Discord avatar refresh."""

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

log = logging.getLogger(__name__)
User = get_user_model()


def _is_test_environment():
    """Check if running in test environment (skip Discord API calls)."""
    return getattr(settings, "TEST", False) and settings.DEBUG


@shared_task
def refresh_discord_avatars(batch_size: int = 100):
    """
    Refresh Discord avatars for users.

    Checks avatar URLs and updates them if they've changed or become invalid.
    Runs periodically via Celery Beat.

    Args:
        batch_size: Number of users to process per run

    Returns:
        dict: Summary of results
    """
    # Skip in test environment to avoid Discord API rate limits
    if _is_test_environment():
        log.info("Skipping Discord avatar refresh in test environment")
        return {"checked": 0, "updated": 0, "failed": 0, "skipped": True}

    from app.utils.avatar_utils import refresh_invalid_avatars

    log.info(f"Starting Discord avatar refresh (batch_size={batch_size})")

    results = refresh_invalid_avatars(batch_size=batch_size)

    log.info(
        f"Avatar refresh complete: checked={results['checked']}, "
        f"updated={results['updated']}, failed={results['failed']}"
    )

    return results


@shared_task
def refresh_single_user_avatar(user_id: int):
    """
    Refresh Discord avatar for a specific user.

    Can be triggered on-demand (e.g., when user logs in).

    Args:
        user_id: The user's ID

    Returns:
        dict: Result of the operation
    """
    # Skip in test environment to avoid Discord API rate limits
    if _is_test_environment():
        log.debug(f"Skipping avatar refresh for user {user_id} in test environment")
        return {"updated": False, "skipped": True}

    from app.utils.avatar_utils import refresh_user_avatar

    log.debug(f"Refreshing avatar for user {user_id}")
    result = refresh_user_avatar(user_id)

    if result.get("updated"):
        log.info(f"Updated avatar for user {user_id}")

    return result


@shared_task
def refresh_all_discord_data():
    """
    Refresh all Discord data for users (avatars, usernames, etc.).

    This is a more comprehensive refresh that can be run less frequently.
    Iterates through all users with Discord IDs in batches.

    Returns:
        dict: Summary of results
    """
    # Skip in test environment to avoid Discord API rate limits
    if _is_test_environment():
        log.info("Skipping full Discord data refresh in test environment")
        return {"checked": 0, "updated": 0, "failed": 0, "skipped": True}

    total_checked = 0
    total_updated = 0
    total_failed = 0
    batch_size = 50

    log.info("Starting full Discord data refresh")

    # Get total count for progress logging
    total_users = User.objects.filter(discordId__isnull=False).count()
    log.info(f"Found {total_users} users with Discord IDs")

    offset = 0
    while True:
        users = User.objects.filter(discordId__isnull=False)[
            offset : offset + batch_size
        ]

        if not users:
            break

        for user in users:
            try:
                total_checked += 1

                # check_and_update_avatar() checks and updates the avatar
                updated = user.check_and_update_avatar()

                if updated:
                    total_updated += 1

            except Exception as e:
                total_failed += 1
                log.error(f"Error refreshing Discord data for user {user.id}: {e}")

        offset += batch_size
        log.debug(f"Processed {offset}/{total_users} users")

    log.info(
        f"Full Discord refresh complete: checked={total_checked}, "
        f"updated={total_updated}, failed={total_failed}"
    )

    return {
        "checked": total_checked,
        "updated": total_updated,
        "failed": total_failed,
    }
