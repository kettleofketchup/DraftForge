"""
Utility functions for Discord avatar management
"""

import logging

from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


def refresh_invalid_avatars(batch_size=50):
    """
    Check and refresh avatars that return 404 errors.

    Args:
        batch_size (int): Number of users to process at once

    Returns:
        dict: Summary of results
    """
    results = {"checked": 0, "updated": 0, "failed": 0, "errors": []}

    # Get users with Discord IDs
    users = User.objects.filter(discordId__isnull=False, avatar__isnull=False).exclude(
        avatar=""
    )[:batch_size]

    for user in users:
        try:
            results["checked"] += 1
            old_avatar = user.avatar

            # This will check the URL and update if needed
            updated = user.check_and_update_avatar()

            if updated:
                results["updated"] += 1
                logging.info(f"Updated avatar for user {user.username}")

        except Exception as e:
            results["failed"] += 1
            error_msg = f"Error processing user {user.username}: {str(e)}"
            results["errors"].append(error_msg)
            logging.error(error_msg)

    return results


def refresh_user_avatar(user_id):
    """
    Refresh avatar for a specific user.

    Args:
        user_id (int): The user's ID

    Returns:
        dict: Result of the operation
    """
    try:
        user = User.objects.get(id=user_id, discordId__isnull=False)
        old_avatar = user.avatar
        updated = user.check_and_update_avatar()

        return {
            "success": True,
            "updated": updated,
            "avatar_url": user.avatarUrl,
            "message": f"Avatar refreshed for {user.username}",
        }
    except User.DoesNotExist:
        return {
            "success": False,
            "message": f"User with ID {user_id} not found or has no Discord ID",
        }
    except Exception as e:
        return {"success": False, "message": f"Error refreshing avatar: {str(e)}"}
