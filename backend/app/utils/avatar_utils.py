"""
Utility functions for Discord avatar management
"""

from typing import Any

from django.contrib.auth import get_user_model

User = get_user_model()


def refresh_user_avatar(user_id: int) -> dict[str, Any]:
    """
    Refresh avatar for a specific user.

    Args:
        user_id (int): The user's ID

    Returns:
        dict: Result of the operation
    """
    try:
        user = User.objects.get(id=user_id, discordId__isnull=False)
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
