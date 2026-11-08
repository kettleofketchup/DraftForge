from typing import Any

from django.utils import timezone

from app.models import CustomUser
from steam.constants import REQUIRED_MATCH_FIELDS, REQUIRED_PLAYER_FIELDS
from steam.models import LeagueSyncState, Match, PlayerMatchStats
from steam.utils.retry import retry_with_backoff
from steam.utils.steam_api_caller import SteamAPI
from telemetry.logging import get_logger

log = get_logger(__name__)


def link_user_to_stats(player_stats: PlayerMatchStats) -> bool:
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
        log.debug(
            "player_linked_to_user",
            system="steam",
            subsystem="league_sync",
            steam_id=player_stats.steam_id,
            username=user.username,
        )
        return True
    except CustomUser.DoesNotExist:
        return False


def relink_all_users() -> int:
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

    log.info(
        "player_stats_relinked",
        system="steam",
        subsystem="league_sync",
        count=linked_count,
    )
    return linked_count


def missing_required_fields(data: dict[str, Any]) -> list[str]:
    """Required match/player fields absent or null in a Steam match payload."""
    missing = {f for f in REQUIRED_MATCH_FIELDS if data.get(f) is None}
    for player in data.get("players", []):
        if player.get("account_id") is not None:
            missing.update(f for f in REQUIRED_PLAYER_FIELDS if player.get(f) is None)
    return sorted(missing)


def process_match(
    match_id: int,
    league_id: int | None = None,
    match_seq_num: int | None = None,
) -> Match | None:
    """
    Fetch single match details from Steam API, store in DB, link users.

    Uses GetMatchHistoryBySequenceNum when match_seq_num is provided (more reliable),
    falls back to GetMatchDetails otherwise.

    Args:
        match_id: Steam match ID
        league_id: Optional league ID to associate with match
        match_seq_num: Optional match sequence number for more reliable fetching

    Returns:
        Match instance or None on failure
    """
    api = SteamAPI()

    def fetch() -> dict[str, Any] | None:
        if match_seq_num:
            # Use GetMatchHistoryBySequenceNum - more reliable for detailed stats
            result = api.get_match_history_by_seq_num(
                match_seq_num, matches_requested=1
            )
            if result and "result" in result:
                matches = result["result"].get("matches", [])
                # Find the specific match by match_id
                for match in matches:
                    if match.get("match_id") == match_id:
                        return {"result": match}
                # If exact match not found, return first match if match_id matches
                if matches and matches[0].get("match_id") == match_id:
                    return {"result": matches[0]}
            return None
        else:
            # Fall back to GetMatchDetails
            return api.get_match_details(match_id)

    success, result = retry_with_backoff(fetch, max_retries=3, base_delay=1.0)

    if not success or not result or "result" not in result:
        log.warning(
            "match_fetch_failed",
            system="steam",
            subsystem="league_sync",
            match_id=match_id,
        )
        return None

    data = result["result"]

    missing = missing_required_fields(data)
    if missing:
        log.info(
            "steam_league_sync_match_unparsed",
            system="steam",
            subsystem="league_sync",
            match_id=match_id,
            league_id=league_id,
            missing_fields=missing,
            reason="steam_api_match_not_yet_parsed",
        )
        return None

    match, created = Match.objects.update_or_create(
        match_id=data["match_id"],
        defaults={
            "radiant_win": data["radiant_win"],
            "duration": data["duration"],
            "start_time": data["start_time"],
            "game_mode": data["game_mode"],
            "lobby_type": data["lobby_type"],
            "league_id": league_id,
        },
    )

    if created:
        log.info(
            "match_stored",
            system="steam",
            subsystem="league_sync",
            match_id=match.match_id,
            league_id=league_id,
            radiant_win=match.radiant_win,
            duration=match.duration,
            start_time=match.start_time,
            game_mode=match.game_mode,
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
                "player_slot": player_data["player_slot"],
                "hero_id": player_data["hero_id"],
                "kills": player_data["kills"],
                "deaths": player_data["deaths"],
                "assists": player_data["assists"],
                "gold_per_min": player_data["gold_per_min"],
                "xp_per_min": player_data["xp_per_min"],
                "last_hits": player_data["last_hits"],
                "denies": player_data["denies"],
                "hero_damage": player_data["hero_damage"],
                "tower_damage": player_data["tower_damage"],
                "hero_healing": player_data["hero_healing"],
            },
        )
        link_user_to_stats(stats)

    return match


def sync_league_matches(league_id: int, full_sync: bool = False) -> dict[str, Any]:
    """
    Main sync entry point. Fetches matches from Steam API and stores them.

    Args:
        league_id: Dota 2 league ID
        full_sync: If True, fetch ALL matches. If False, only new matches.

    Returns:
        dict: {synced_count, failed_count, new_last_match_id}
    """
    state, _ = LeagueSyncState.objects.get_or_create(
        league_id=league_id, defaults={"failed_match_ids": []}
    )

    if state.is_syncing:
        log.warning(
            "league_sync_already_running",
            system="steam",
            subsystem="league_sync",
            league_id=league_id,
        )
        return {
            "error": "Sync already in progress",
            "synced_count": 0,
            "failed_count": 0,
        }

    state.is_syncing = True
    state.save()

    api = SteamAPI()
    synced_count = 0
    failed_count = 0
    failed_ids = list(state.failed_match_ids)
    # Always start from newest matches. GetMatchHistory with start_at_match_id
    # returns matches OLDER than that ID, so passing last_match_id would only
    # return already-seen matches. Instead, start from None (newest) and
    # paginate backward until we hit known territory.
    start_at_match_id = None
    new_last_match_id = state.last_match_id

    try:
        while True:
            result = api.get_match_history(
                league_id=league_id,
                start_at_match_id=start_at_match_id,
                matches_requested=100,
            )

            if not result or "result" not in result:
                log.error(
                    "match_history_fetch_failed",
                    system="steam",
                    subsystem="league_sync",
                    league_id=league_id,
                )
                break

            matches = result["result"].get("matches", [])
            if not matches:
                break

            caught_up = False
            for match_data in matches:
                match_id = match_data["match_id"]
                match_seq_num = match_data.get("match_seq_num")

                # Skip if we've already processed this in incremental sync
                if (
                    not full_sync
                    and state.last_match_id
                    and match_id <= state.last_match_id
                ):
                    caught_up = True
                    continue

                match = process_match(
                    match_id, league_id=league_id, match_seq_num=match_seq_num
                )

                if match:
                    synced_count += 1
                    if match_id in failed_ids:
                        failed_ids.remove(match_id)
                    if new_last_match_id is None or match_id > new_last_match_id:
                        new_last_match_id = match_id
                else:
                    failed_count += 1
                    if match_id not in failed_ids:
                        failed_ids.append(match_id)

            # Pagination: use the last match_id to get older matches
            start_at_match_id = matches[-1]["match_id"]

            # For incremental sync, stop once we've reached already-known matches
            if not full_sync and caught_up:
                break

    finally:
        state.is_syncing = False
        state.last_sync_at = timezone.now()
        state.last_match_id = new_last_match_id
        state.failed_match_ids = failed_ids
        state.save()

    log.info(
        "league_sync_complete",
        system="steam",
        subsystem="league_sync",
        league_id=league_id,
        synced_count=synced_count,
        failed_count=failed_count,
        new_last_match_id=new_last_match_id,
    )

    return {
        "synced_count": synced_count,
        "failed_count": failed_count,
        "new_last_match_id": new_last_match_id,
    }


def retry_failed_matches(league_id: int) -> dict[str, int]:
    """
    Attempt to re-process matches in failed_match_ids.
    Clears successful ones from the list.

    Args:
        league_id: Dota 2 league ID

    Returns:
        dict: {retried_count, still_failed_count}
    """
    try:
        state = LeagueSyncState.objects.get(league_id=league_id)
    except LeagueSyncState.DoesNotExist:
        return {"retried_count": 0, "still_failed_count": 0}

    failed_ids = list(state.failed_match_ids)
    still_failed = []
    retried_count = 0

    for match_id in failed_ids:
        match = process_match(match_id, league_id=league_id)
        if match:
            retried_count += 1
        else:
            still_failed.append(match_id)

    state.failed_match_ids = still_failed
    state.save()

    log.info(
        "league_retry_complete",
        system="steam",
        subsystem="league_sync",
        league_id=league_id,
        retried_count=retried_count,
        still_failed_count=len(still_failed),
    )

    return {
        "retried_count": retried_count,
        "still_failed_count": len(still_failed),
    }
