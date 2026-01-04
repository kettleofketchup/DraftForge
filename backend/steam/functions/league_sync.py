import logging

from app.models import CustomUser
from steam.models import Match, PlayerMatchStats
from steam.utils.retry import retry_with_backoff
from steam.utils.steam_api_caller import SteamAPI

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


def process_match(match_id, league_id=None):
    """
    Fetch single match details from Steam API, store in DB, link users.

    Args:
        match_id: Steam match ID
        league_id: Optional league ID to associate with match

    Returns:
        Match instance or None on failure
    """
    api = SteamAPI()

    def fetch():
        return api.get_match_details(match_id)

    success, result = retry_with_backoff(fetch, max_retries=3, base_delay=1.0)

    if not success or not result or "result" not in result:
        log.warning(f"Failed to fetch match {match_id}")
        return None

    data = result["result"]

    match, _ = Match.objects.update_or_create(
        match_id=data["match_id"],
        defaults={
            "radiant_win": data.get("radiant_win", False),
            "duration": data.get("duration", 0),
            "start_time": data.get("start_time", 0),
            "game_mode": data.get("game_mode", 0),
            "lobby_type": data.get("lobby_type", 0),
            "league_id": league_id,
        },
    )

    for player_data in data.get("players", []):
        account_id = player_data.get("account_id")
        if account_id is None:
            continue

        # Convert 32-bit account_id to 64-bit steam_id
        steam_id_64 = account_id + 76561197960265728

        stats, _ = PlayerMatchStats.objects.update_or_create(
            match=match,
            steam_id=steam_id_64,
            defaults={
                "player_slot": player_data.get("player_slot", 0),
                "hero_id": player_data.get("hero_id", 0),
                "kills": player_data.get("kills", 0),
                "deaths": player_data.get("deaths", 0),
                "assists": player_data.get("assists", 0),
                "gold_per_min": player_data.get("gold_per_min", 0),
                "xp_per_min": player_data.get("xp_per_min", 0),
                "last_hits": player_data.get("last_hits", 0),
                "denies": player_data.get("denies", 0),
                "hero_damage": player_data.get("hero_damage", 0),
                "tower_damage": player_data.get("tower_damage", 0),
                "hero_healing": player_data.get("hero_healing", 0),
            },
        )
        link_user_to_stats(stats)

    return match
