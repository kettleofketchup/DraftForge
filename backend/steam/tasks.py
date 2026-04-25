"""Celery tasks for Steam league sync.

All DB operations via internal HTTP API — no ORM imports.
Workers can run off-host with only broker + backend URL access.
"""

import logging

from celery import shared_task

from app.internal_client import (
    get_steam_sync_state,
    recalculate_user_mmr,
    store_steam_match,
    update_league_stats,
    update_steam_sync_state,
)
from steam.constants import LEAGUE_ID
from steam.utils.retry import retry_with_backoff
from steam.utils.steam_api_caller import SteamAPI

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_league_matches_task(self, league_id: int = None):
    """
    Fetch new matches from Steam API, store via internal API.
    Scheduled to run every minute.
    """
    if league_id is None:
        league_id = LEAGUE_ID

    logger.info(f"Starting league sync for league {league_id}")

    # 1. Check sync state
    state = get_steam_sync_state(league_id)
    if not state:
        logger.error("Failed to fetch sync state from internal API")
        raise self.retry(countdown=60)

    if state["is_syncing"]:
        logger.warning(f"Sync already in progress for league {league_id}")
        return {"synced_count": 0, "failed_count": 0, "error": "Already syncing"}

    # 2. Mark as syncing
    update_steam_sync_state(league_id, is_syncing=True)

    api = SteamAPI()
    synced_count = 0
    failed_count = 0
    start_at_match_id = None
    new_last_match_id = state["last_match_id"]

    try:
        while True:
            result = api.get_match_history(
                league_id=league_id,
                start_at_match_id=start_at_match_id,
                matches_requested=100,
            )

            if not result or "result" not in result:
                logger.error(f"Failed to fetch match history for league {league_id}")
                break

            matches = result["result"].get("matches", [])
            if not matches:
                break

            caught_up = False
            for match_data in matches:
                match_id = match_data["match_id"]
                match_seq_num = match_data.get("match_seq_num")

                # Skip already-processed matches
                if state["last_match_id"] and match_id <= state["last_match_id"]:
                    caught_up = True
                    continue

                # Fetch full match details from Steam and store via API
                stored = _fetch_and_store_match(api, match_id, match_seq_num, league_id)

                if stored:
                    synced_count += 1
                    if new_last_match_id is None or match_id > new_last_match_id:
                        new_last_match_id = match_id
                else:
                    failed_count += 1

            start_at_match_id = matches[-1]["match_id"]

            if caught_up:
                break

    finally:
        update_steam_sync_state(
            league_id,
            is_syncing=False,
            last_match_id=new_last_match_id,
        )

    # Trigger stats update if new matches were synced
    if synced_count > 0:
        update_league_stats_task.delay(league_id)

    logger.info(
        f"League sync complete: {synced_count} synced, {failed_count} failed"
    )

    return {"synced_count": synced_count, "failed_count": failed_count}


def _fetch_and_store_match(api, match_id, match_seq_num, league_id):
    """Fetch match from Steam API and store via internal endpoint."""

    def fetch():
        if match_seq_num:
            result = api.get_match_history_by_seq_num(
                match_seq_num, matches_requested=1
            )
            if result and "result" in result:
                for m in result["result"].get("matches", []):
                    if m.get("match_id") == match_id:
                        return {"result": m}
            return None
        else:
            return api.get_match_details(match_id)

    success, result = retry_with_backoff(fetch, max_retries=3, base_delay=1.0)

    if not success or not result or "result" not in result:
        logger.warning(f"Failed to fetch match {match_id} from Steam")
        return False

    data = result["result"]

    # POST to backend for DB storage
    stored = store_steam_match({
        "match_id": data["match_id"],
        "league_id": league_id,
        "radiant_win": data.get("radiant_win", False),
        "duration": data.get("duration", 0),
        "start_time": data.get("start_time", 0),
        "game_mode": data.get("game_mode", 0),
        "lobby_type": data.get("lobby_type", 0),
        "players": data.get("players", []),
    })

    return stored is not None


@shared_task(bind=True)
def update_league_stats_task(self, league_id: int = None):
    """Update LeaguePlayerStats for all users in a league via internal API."""
    if league_id is None:
        league_id = LEAGUE_ID

    logger.info(f"Updating league stats for league {league_id}")

    updated_count = update_league_stats(league_id)
    if updated_count is None:
        logger.error("Failed to update league stats via internal API")
        return {"updated_count": 0, "error": "API call failed"}

    logger.info(f"Updated stats for {updated_count} users")
    return {"updated_count": updated_count}


@shared_task
def recalculate_user_league_mmr_task(user_id: int):
    """Recalculate a single user's league_mmr via internal API."""
    result = recalculate_user_mmr(user_id)
    if result is None:
        logger.error(f"Failed to recalculate MMR for user {user_id}")
        return None

    logger.info(f"Recalculated league MMR for user {user_id}")
    return result
