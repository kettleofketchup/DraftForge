"""Steam sync: league sync state, match storage, league stats and MMR."""

from typing import Any

import requests

from app.internal_client import transport


def get_steam_sync_state(league_id: int) -> dict[str, Any] | None:
    """Get LeagueSyncState for a league (creates if missing)."""
    resp = transport.get(f"/steam/sync-state/{league_id}/")
    if resp and resp.ok:
        return resp.json()
    return None


def get_tracked_steam_league_ids() -> list[int] | None:
    """Return list of League.steam_league_id values currently configured.

    Returns None on transport error so the caller can distinguish that
    from a legitimate empty list (no League has steam_league_id set).
    """
    resp = transport.get("/steam/tracked-leagues/")
    if resp and resp.ok:
        return resp.json().get("steam_league_ids", [])
    return None


def update_steam_sync_state(league_id: int, **fields: Any) -> bool:
    """Update sync state fields. Returns True on success."""
    resp = transport.patch(f"/steam/sync-state/{league_id}/", fields)
    return resp is not None and resp.ok


def store_steam_match(match_data: dict) -> tuple[dict | None, int | None]:
    """Store a match + player stats.

    Returns (payload, status_code):
      - (dict, 2xx)  on success
      - (None, 422)  when Steam hasn't parsed the match yet
                     (response: {"error": "match_unparsed", ...})
      - (None, 4xx/5xx) for other server-side errors
      - (None, None) when the internal API was unreachable
    """
    resp = transport.post("/steam/store-match/", match_data)
    if resp is None:
        return None, None
    if resp.ok:
        return resp.json(), resp.status_code
    return None, resp.status_code


def update_league_stats(league_id: int) -> int | None:
    """Trigger league stats recalculation. Returns updated_count or None."""
    resp = transport.post(f"/steam/update-league-stats/{league_id}/", {})
    if resp and resp.ok:
        return resp.json().get("updated_count")
    return None


def recalculate_user_mmr(user_id: int) -> dict[str, Any] | None:
    """Recalculate a user's league MMR. Returns response dict or None."""
    resp = transport.post(f"/steam/recalculate-mmr/{user_id}/", {})
    if resp and resp.ok:
        return resp.json()
    return None


def batch_upsert_matches(data: dict[str, Any]) -> requests.Response | None:
    """Batch create/update Match + PlayerMatchStats records."""
    return transport.post("/steam/matches/", data)


def update_sync_state(pk: int, **data: Any) -> requests.Response | None:
    """Update LeagueSyncState after sync."""
    return transport.patch(f"/steam/sync-state/{pk}/", data)
