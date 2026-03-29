"""HTTP client for internal API calls from celery workers and Discord bot.

All external processes MUST use this client instead of importing Django models.
Django/Daphne is the sole DB reader/writer.

Config:
    INTERNAL_API_URL: defaults to http://backend:8000/api/internal (Docker).
                      Set to https://dota.kettle.sh/api/internal for remote.
    INTERNAL_SERVICE_TOKEN: shared secret for X-Internal-Token header.
"""

import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

INTERNAL_API_URL = os.environ.get(
    "INTERNAL_API_URL",
    "http://backend:8000/api/internal",
)
# Base API URL for reads — same host, public API paths
API_BASE_URL = os.environ.get(
    "API_BASE_URL",
    "http://backend:8000/api",
)
TIMEOUT = 30


def _headers():
    return {
        "X-Internal-Token": getattr(settings, "INTERNAL_SERVICE_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _post(path, data):
    """POST to an internal endpoint. Returns response or None on network error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.post(url, json=data, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error(
                "Internal POST %s: %s %s", path, resp.status_code, resp.text[:200]
            )
        return resp
    except requests.RequestException:
        logger.exception("Internal POST %s failed", path)
        return None


def _patch(path, data):
    """PATCH an internal endpoint. Returns response or None on network error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.patch(url, json=data, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error(
                "Internal PATCH %s: %s %s", path, resp.status_code, resp.text[:200]
            )
        return resp
    except requests.RequestException:
        logger.exception("Internal PATCH %s failed", path)
        return None


def _get(path, params=None):
    """GET from an internal endpoint. Returns response or None on network error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error(
                "Internal GET %s: %s %s", path, resp.status_code, resp.text[:200]
            )
        return resp
    except requests.RequestException:
        logger.exception("Internal GET %s failed", path)
        return None


# ---- Discord writes ----


def create_message_log(**data):
    """Create DiscordMessageLog entry."""
    return _post("/discord/message-log/", data)


def create_event_log(**data):
    """Create DiscordEventLog audit entry."""
    return _post("/discord/event-log/", data)


def create_tournament_log(**data):
    """Create DiscordTournamentLog entry."""
    return _post("/discord/tournament-log/", data)


def get_or_create_discord_event(**data):
    """Get or create DiscordEvent for an event."""
    return _post("/discord/events/get-or-create/", data)


def update_discord_event(pk, **data):
    """Update DiscordEvent fields (scheduled_event_id, etc.)."""
    return _patch(f"/discord/events/{pk}/", data)


def create_or_update_signup_message(**data):
    """Create/update DiscordEventMsgSignup record."""
    return _post("/discord/signup-message/", data)


def create_or_update_announcement(**data):
    """Create/update DiscordEventMsgAnnouncement record."""
    return _post("/discord/announcement/", data)


def update_scheduled_event(pk, **data):
    """Update ScheduledEvent fields (discord_message_id, next_post_at)."""
    return _patch(f"/discord/scheduled-events/{pk}/", data)


def create_event_dm(**data):
    """Create DiscordEventDM record (crash-safe: create before send)."""
    return _post("/discord/event-dm/", data)


def update_event_dm(pk, **data):
    """Update DiscordEventDM delivery status after DM sent."""
    return _patch(f"/discord/event-dm/{pk}/", data)


# ---- Event writes ----


def transition_event_state(event_pk, new_state):
    """Transition event to a new state."""
    return _post(f"/events/{event_pk}/transition/", {"state": new_state})


# ---- Reads via public API (internal token accepted globally) ----


def _api_get(path, params=None):
    """GET from the public API (not /internal/). Uses same auth token."""
    url = f"{API_BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("API GET %s: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException:
        logger.exception("API GET %s failed", path)
        return None


def get_event(pk):
    """Get event data by PK via public API."""
    return _api_get(f"/events/{pk}/")


def get_event_for_task(pk):
    """Get full event data + org Discord config for celery tasks.

    Returns EventTaskData (Pydantic) with typed attribute access,
    or None if event not found / API error.
    """
    from app.schemas import EventTaskData

    resp = _get(f"/events/{pk}/full/")
    if resp and resp.ok:
        return EventTaskData.model_validate(resp.json())
    return None


def get_events(params=None):
    """List events with filters via public API."""
    return _api_get("/events/", params=params)


def get_event_signups(event_pk):
    """Get signups for an event via public API."""
    return _api_get(f"/events/signups/", params={"event": event_pk})


def check_message_log_exists(source, source_id):
    """Check if a successful DiscordMessageLog exists for idempotency."""
    resp = _get("/discord/check-log/", {"source": source, "source_id": source_id})
    if resp and resp.ok:
        return resp.json().get("exists", False)
    return False


def search_message_logs(**params):
    """Search DiscordMessageLog entries. Returns list of MessageLogEntry."""
    from app.schemas import MessageLogEntry

    resp = _get("/discord/message-logs/", params)
    if resp and resp.ok:
        return [MessageLogEntry.model_validate(e) for e in resp.json()]
    return []


def get_discord_event_state(event_id):
    """Get Discord event state (DiscordEvent, logs, DMs) for an event."""
    resp = _get(f"/discord/event-state/{event_id}/")
    if resp and resp.ok:
        return resp.json()
    return None


def get_fired_message_sources(event_id):
    """Get set of fired log sources for an event (for sync_discord_events)."""
    logs = search_message_logs(
        source_id=event_id,
        success="true",
        limit=100,
    )
    return {log["source"] for log in logs}


def get_first_message_log(source, source_id):
    """Get the most recent successful message log for a source+source_id."""
    logs = search_message_logs(
        source=source, source_id=source_id, success="true", limit=1
    )
    return logs[0] if logs else None


def get_sync_discord_state():
    """Get bulk Discord sync state. Returns SyncDiscordState or None."""
    from app.schemas import SyncDiscordState

    resp = _get("/discord/sync-state/")
    if resp and resp.ok:
        return SyncDiscordState.model_validate(resp.json())
    return None


def get_discord_event_state(event_id):
    """Get Discord event state. Returns DiscordEventState or None."""
    from app.schemas import DiscordEventState

    resp = _get(f"/discord/event-state/{event_id}/")
    if resp and resp.ok:
        return DiscordEventState.model_validate(resp.json())
    return None


def get_repeater_subscribers(repeater_id):
    """Get subscribers for a repeater. Returns list of RepeaterSubscriber."""
    from app.schemas import RepeaterSubscriber

    resp = _get(f"/repeaters/{repeater_id}/subscribers/")
    if resp and resp.ok:
        return [RepeaterSubscriber.model_validate(s) for s in resp.json()]
    return []


def get_due_scheduled_events():
    """Get ScheduledEvents due for posting. Returns list of ScheduledEventDue."""
    from app.schemas import ScheduledEventDue

    resp = _get("/scheduled-events/due/")
    if resp and resp.ok:
        return [ScheduledEventDue.model_validate(e) for e in resp.json()]
    return []


# ---- Steam writes ----


def batch_upsert_matches(data):
    """Batch create/update Match + PlayerMatchStats records."""
    return _post("/steam/matches/", data)


def update_sync_state(pk, **data):
    """Update LeagueSyncState after sync."""
    return _patch(f"/steam/sync-state/{pk}/", data)


# ---- User writes ----


def update_user_avatar(pk, avatar_url):
    """Update CustomUser avatar field."""
    return _patch(f"/users/{pk}/avatar/", {"avatar": avatar_url})


# ---- Tournament reads ----


def get_tournament_for_task(pk):
    """Get tournament config for Celery tasks. Returns TournamentTaskData or None."""
    from app.schemas import TournamentTaskData

    resp = _get(f"/tournaments/{pk}/full/")
    if resp and resp.ok:
        return TournamentTaskData.model_validate(resp.json())
    return None


def get_tournament_participants(tournament_id):
    """Get participants with Discord IDs. Returns list of TournamentParticipant."""
    from app.schemas import TournamentParticipant

    resp = _get(f"/tournaments/{tournament_id}/participants/")
    if resp and resp.ok:
        return [TournamentParticipant.model_validate(p) for p in resp.json()]
    return []


def get_match_participants(game_id):
    """Get match players with Discord IDs. Returns list of TournamentParticipant."""
    from app.schemas import TournamentParticipant

    resp = _get(f"/games/{game_id}/participants/")
    if resp and resp.ok:
        return [TournamentParticipant.model_validate(p) for p in resp.json()]
    return []


def get_games_without_herodraft(tournament_id):
    """Get games needing hero drafts. Returns list of GameWithoutHeroDraft."""
    from app.schemas import GameWithoutHeroDraft

    resp = _get(f"/tournaments/{tournament_id}/games-without-herodraft/")
    if resp and resp.ok:
        return [GameWithoutHeroDraft.model_validate(g) for g in resp.json()]
    return []


# ---- Tournament writes ----


def create_herodraft_for_game(game_id):
    """Atomically create a HeroDraft for a game. Returns response or None."""
    return _post(f"/games/{game_id}/create-herodraft/", {})
