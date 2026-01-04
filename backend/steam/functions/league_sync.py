import logging

from app.models import CustomUser
from steam.models import PlayerMatchStats

log = logging.getLogger(__name__)


def link_user_to_stats(player_stats):
    """
    Attempt to link a PlayerMatchStats record to a CustomUser via steamid.

    Args:
        player_stats: PlayerMatchStats instance

    Returns:
        bool: True if linked successfully, False otherwise
    """
    if player_stats.user:
        return True  # Already linked

    try:
        user = CustomUser.objects.get(steamid=player_stats.steam_id)
        player_stats.user = user
        player_stats.save(update_fields=["user"])
        log.debug(f"Linked player {player_stats.steam_id} to user {user.username}")
        return True
    except CustomUser.DoesNotExist:
        return False


def relink_all_users():
    """
    Re-scan all PlayerMatchStats and attempt to link unlinked records to users.

    Returns:
        int: Number of successfully linked records
    """
    unlinked_stats = PlayerMatchStats.objects.filter(user__isnull=True)
    linked_count = 0

    for stats in unlinked_stats:
        if link_user_to_stats(stats):
            linked_count += 1

    log.info(f"Relinked {linked_count} player stats to users")
    return linked_count
