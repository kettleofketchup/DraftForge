"""Celery tasks for Steam league sync.

All DB operations via internal HTTP API — no ORM imports.
Workers can run off-host with only broker + backend URL access.
"""

import time

from celery import shared_task

from app.internal_client import (
    get_steam_sync_state,
    get_tracked_steam_league_ids,
    recalculate_user_mmr,
    store_steam_match,
    update_league_stats,
    update_steam_sync_state,
)
from steam.utils.retry import retry_with_backoff
from steam.utils.steam_api_caller import SteamAPI
from telemetry.logging import get_logger

log = get_logger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_all_steam_leagues_task(self):
    """Periodic coordinator — fan out one `sync_league_matches_task` per
    League row that has `steam_league_id` set.

    Replaces the prior beat entry that called `sync_league_matches_task`
    directly with no argument and silently fell back to a hardcoded
    constant, pinning the periodic sync to a single league regardless
    of DB configuration.

    Dispatch is via `.delay()` so each league becomes its own job. Steam
    API pressure is bounded by `sync_league_matches_task`'s own
    `rate_limit` — workers process one league at a time at most one per
    second, no matter how many leagues are tracked.
    """
    league_ids = get_tracked_steam_league_ids()
    if league_ids is None:
        log.error(
            "steam_sync_fanout_state_fetch_failed",
            system="steam",
            subsystem="sync",
            reason="internal_api_returned_none",
        )
        raise self.retry(countdown=60)

    log.info(
        "steam_sync_fanout_dispatch",
        system="steam",
        subsystem="sync",
        league_count=len(league_ids),
        league_ids=league_ids,
    )

    for league_id in league_ids:
        sync_league_matches_task.delay(league_id)

    return {"dispatched": len(league_ids), "league_ids": league_ids}


@shared_task(bind=True, max_retries=3, rate_limit="60/m")
def sync_league_matches_task(self, league_id: int):
    """Fetch new matches from Steam API for a single league, store via internal API.

    Dispatched per-league by `sync_all_steam_leagues_task`; never scheduled
    directly anymore. The `rate_limit="60/m"` is a backstop against
    Steam API abuse if many leagues are tracked — celery will serialize
    task starts to at most one per second per worker. Each task itself
    may issue multiple Steam calls (1 history + N detail per new match);
    the cursor-based incremental sync keeps steady-state at one history
    call per tick.
    """
    started_at = time.monotonic()

    # 1. Check sync state
    state = get_steam_sync_state(league_id)
    if not state:
        log.error(
            "steam_sync_state_fetch_failed",
            system="steam",
            subsystem="sync",
            league_id=league_id,
            reason="internal_api_returned_none",
        )
        raise self.retry(countdown=60)

    prior_last_match_id = state["last_match_id"]
    log.info(
        "steam_sync_start",
        system="steam",
        subsystem="sync",
        league_id=league_id,
        prior_last_match_id=prior_last_match_id,
        failed_match_ids_count=len(state.get("failed_match_ids") or []),
    )

    if state["is_syncing"]:
        log.warning(
            "steam_sync_skipped",
            system="steam",
            subsystem="sync",
            league_id=league_id,
            reason="already_syncing",
        )
        return {"synced_count": 0, "failed_count": 0, "error": "Already syncing"}

    # 2. Mark as syncing
    update_steam_sync_state(league_id, is_syncing=True)

    api = SteamAPI()
    synced_count = 0
    failed_count = 0
    skipped_count = 0
    batches_fetched = 0
    start_at_match_id = None
    new_last_match_id = prior_last_match_id

    try:
        while True:
            batches_fetched += 1
            result = api.get_match_history(
                league_id=league_id,
                start_at_match_id=start_at_match_id,
                matches_requested=100,
            )

            if not result or "result" not in result:
                log.error(
                    "steam_api_history_fetch_failed",
                    system="steam",
                    subsystem="sync",
                    league_id=league_id,
                    start_at_match_id=start_at_match_id,
                    batch_num=batches_fetched,
                )
                break

            matches = result["result"].get("matches", [])
            if not matches:
                log.info(
                    "steam_api_history_empty",
                    system="steam",
                    subsystem="sync",
                    league_id=league_id,
                    start_at_match_id=start_at_match_id,
                    batch_num=batches_fetched,
                    reason=(
                        "no_matches_for_league"
                        if batches_fetched == 1
                        else "end_of_history"
                    ),
                )
                break

            batch_first_match_id = matches[0]["match_id"]
            batch_last_match_id = matches[-1]["match_id"]
            batch_new = 0
            batch_skipped = 0
            batch_failed = 0

            caught_up = False
            for match_data in matches:
                match_id = match_data["match_id"]
                match_seq_num = match_data.get("match_seq_num")

                # Skip already-processed matches
                if state["last_match_id"] and match_id <= state["last_match_id"]:
                    caught_up = True
                    batch_skipped += 1
                    skipped_count += 1
                    continue

                # Fetch full match details from Steam and store via API
                stored = _fetch_and_store_match(api, match_id, match_seq_num, league_id)

                if stored:
                    synced_count += 1
                    batch_new += 1
                    if new_last_match_id is None or match_id > new_last_match_id:
                        new_last_match_id = match_id
                else:
                    failed_count += 1
                    batch_failed += 1

            log.info(
                "steam_sync_batch",
                system="steam",
                subsystem="sync",
                league_id=league_id,
                batch_num=batches_fetched,
                batch_size=len(matches),
                batch_first_match_id=batch_first_match_id,
                batch_last_match_id=batch_last_match_id,
                batch_new=batch_new,
                batch_skipped=batch_skipped,
                batch_failed=batch_failed,
                caught_up=caught_up,
            )

            start_at_match_id = batch_last_match_id

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

    log.info(
        "steam_sync_complete",
        system="steam",
        subsystem="sync",
        league_id=league_id,
        synced_count=synced_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        batches_fetched=batches_fetched,
        prior_last_match_id=prior_last_match_id,
        new_last_match_id=new_last_match_id,
        advanced_cursor=new_last_match_id != prior_last_match_id,
        duration_ms=int((time.monotonic() - started_at) * 1000),
    )

    return {
        "synced_count": synced_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
    }


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
        log.warning(
            "steam_match_fetch_failed",
            system="steam",
            subsystem="sync",
            match_id=match_id,
            match_seq_num=match_seq_num,
            league_id=league_id,
            fetch_method="seq_num" if match_seq_num else "match_details",
        )
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

    if stored is None:
        log.warning(
            "steam_match_store_failed",
            system="steam",
            subsystem="sync",
            match_id=match_id,
            league_id=league_id,
            reason="internal_api_returned_none",
        )
        return False

    log.info(
        "steam_match_stored",
        system="steam",
        subsystem="sync",
        match_id=match_id,
        league_id=league_id,
        created=stored.get("created"),
        players_stored=stored.get("players_stored"),
        players_linked=stored.get("players_linked"),
    )
    return True


@shared_task(bind=True)
def update_league_stats_task(self, league_id: int):
    """Update LeaguePlayerStats for all users in a league via internal API."""
    log.info(
        "steam_league_stats_start",
        system="steam",
        subsystem="stats",
        league_id=league_id,
    )

    updated_count = update_league_stats(league_id)
    if updated_count is None:
        log.error(
            "steam_league_stats_failed",
            system="steam",
            subsystem="stats",
            league_id=league_id,
            reason="internal_api_returned_none",
        )
        return {"updated_count": 0, "error": "API call failed"}

    log.info(
        "steam_league_stats_complete",
        system="steam",
        subsystem="stats",
        league_id=league_id,
        updated_count=updated_count,
    )
    return {"updated_count": updated_count}


@shared_task
def recalculate_user_league_mmr_task(user_id: int):
    """Recalculate a single user's league_mmr via internal API."""
    result = recalculate_user_mmr(user_id)
    if result is None:
        log.error(
            "steam_user_mmr_recalc_failed",
            system="steam",
            subsystem="mmr",
            user_id=user_id,
        )
        return None

    log.info(
        "steam_user_mmr_recalc_complete",
        system="steam",
        subsystem="mmr",
        user_id=user_id,
    )
    return result
