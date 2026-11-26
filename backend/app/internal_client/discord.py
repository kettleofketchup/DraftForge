"""Discord state: message-log leases and reads, event/tournament logs, Discord
events, signup/announcement messages, scheduled-event and DM records, sync state."""

from typing import TYPE_CHECKING, Any

import requests

from app.internal_client import transport
from discordbot.delivery_types import ClaimResult
from discordbot.schemas import (
    DiscordEventStateSchema,
    MessageLogSchema,
    SyncDiscordStateSchema,
)
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from discordbot.schemas import (
        DiscordEventStateSchema,
        MessageLogSchema,
        SyncDiscordStateSchema,
    )

logger = get_logger(__name__)


# ---- Activity ----


def create_activity_notification_invite(kind: str, draft_id: int) -> str | None:
    """Long-lived Activity invite for a draft's shared voice channel, if it has one."""
    resp = transport.post(
        "/discord/activity-notification-invite/",
        {"kind": kind, "draft_id": draft_id},
    )
    if not resp or not resp.ok:
        return None
    try:
        url = resp.json().get("url")
    except (ValueError, AttributeError):
        return None
    if isinstance(url, str) and url.startswith("https://discord.gg/"):
        return url
    return None


# ---- Message logs ----


def create_message_log(**data: Any) -> requests.Response | None:
    """Create DiscordMessageLog entry."""
    return transport.post("/discord/message-log/", data)


def claim_discord_message_log_result(
    *,
    source: str,
    source_id: int,
    channel_id: str,
    embed_data: dict,
    fired_by_user_id: int | None = None,
    tournament_log_id: int | None = None,
) -> ClaimResult:
    """Distinguish an acquired lease, contention, and unavailable claim state."""
    payload: dict[str, Any] = {
        "source": source,
        "source_id": source_id,
        "channel_id": channel_id,
        "embed_data": embed_data,
    }
    if fired_by_user_id is not None:
        payload["fired_by_user_id"] = fired_by_user_id
    if tournament_log_id is not None:
        payload["tournament_log_id"] = tournament_log_id

    resp = transport.post("/discord/message-log/claim/", payload)
    if resp is None:
        return ClaimResult("unavailable")
    if resp.status_code == 409:
        return ClaimResult("held")
    if resp.status_code != 201:
        return ClaimResult("unavailable")
    try:
        data = resp.json()
    except ValueError:
        return ClaimResult("unavailable")
    log_id = data.get("id") if isinstance(data, dict) else None
    if type(log_id) is not int or log_id <= 0:
        return ClaimResult("unavailable")
    return ClaimResult("claimed", log_id)


def claim_discord_message_log(
    *,
    source: str,
    source_id: int,
    channel_id: str,
    embed_data: dict,
    fired_by_user_id: int | None = None,
    tournament_log_id: int | None = None,
) -> int | None:
    return claim_discord_message_log_result(
        source=source,
        source_id=source_id,
        channel_id=channel_id,
        embed_data=embed_data,
        fired_by_user_id=fired_by_user_id,
        tournament_log_id=tournament_log_id,
    ).log_id


def finalize_discord_message_log(
    log_id: int,
    *,
    success: bool,
    discord_message_id: str | None = None,
    status_code: int | None = None,
    response_data: dict | None = None,
) -> requests.Response | None:
    """Update the lease row to its final state after the Discord HTTP send.

    Silently no-ops on 410 Gone — that means sweep_stale_discord_leases
    reaped the row before finalize landed (rare, only on slow workers).
    """
    payload: dict[str, Any] = {"success": success}
    if discord_message_id is not None:
        payload["discord_message_id"] = discord_message_id
    if status_code is not None:
        payload["status_code"] = status_code
    if response_data is not None:
        payload["response_data"] = response_data

    return transport.post(f"/discord/message-log/{log_id}/finalize/", payload)


def check_message_log_exists(source: str, source_id: int) -> bool:
    """Check if a successful DiscordMessageLog exists for idempotency."""
    resp = transport.get(
        "/discord/check-log/", {"source": source, "source_id": source_id}
    )
    if resp and resp.ok:
        return resp.json().get("exists", False)
    return False


def search_message_logs(**params: Any) -> list["MessageLogSchema"]:
    """Search DiscordMessageLog entries. Returns list of MessageLogSchema."""

    resp = transport.get("/discord/message-logs/", params)
    if resp and resp.ok:
        return [MessageLogSchema.model_validate(e) for e in resp.json()]
    return []


def get_fired_message_sources(event_id: int) -> set[str]:
    """Get set of fired log sources for an event (for sync_discord_events)."""
    logs = search_message_logs(
        source_id=event_id,
        success="true",
        limit=100,
    )
    return {log.source for log in logs}


def get_first_message_log(source: str, source_id: int) -> "MessageLogSchema | None":
    """Get the most recent successful message log for a source+source_id."""
    logs = search_message_logs(
        source=source, source_id=source_id, success="true", limit=1
    )
    return logs[0] if logs else None


def sweep_discord_leases(
    pending_threshold_minutes: int = 5, failed_threshold_hours: int = 1
) -> dict[str, int]:
    """Reap stuck DiscordMessageLog rows.

    Renamed from `sweep_stale_discord_leases` so callers can `import` it
    without colliding with the celery task of the same name in
    `discordbot/tasks.py`.

    Returns {pending_swept, failed_swept, total} on success, or
    {pending_swept: 0, failed_swept: 0, total: 0} on failure (so callers
    can treat the return value as truthy/falsy without crashing).
    """
    resp = transport.post(
        "/discord/sweep-stale-leases/",
        {
            "pending_threshold_minutes": pending_threshold_minutes,
            "failed_threshold_hours": failed_threshold_hours,
        },
    )
    if resp is None or not resp.ok:
        return {"pending_swept": 0, "failed_swept": 0, "total": 0}
    try:
        return resp.json()
    except ValueError:
        logger.error(
            "sweep_stale_leases_invalid_json",
            system="internal_client",
            subsystem="http",
            body_excerpt=resp.text[:200],
        )
        return {"pending_swept": 0, "failed_swept": 0, "total": 0}


# ---- Audit logs ----


def create_event_log(**data: Any) -> requests.Response | None:
    """Create DiscordEventLog audit entry."""
    return transport.post("/discord/event-log/", data)


def create_tournament_log(**data: Any) -> requests.Response | None:
    """Create DiscordTournamentLog entry."""
    return transport.post("/discord/tournament-log/", data)


def update_tournament_log(pk: int, **data: Any) -> requests.Response | None:
    """Update DiscordTournamentLog entry (recipient_count, message, success)."""
    return transport.patch(f"/discord/tournament-log/{pk}/", data)


# ---- Discord events, signup and announcement messages ----


def get_or_create_discord_event(**data: Any) -> requests.Response | None:
    """Get or create DiscordEvent for an event."""
    return transport.post("/discord/events/get-or-create/", data)


def update_discord_event(pk: int, **data: Any) -> requests.Response | None:
    """Update DiscordEvent fields (scheduled_event_id, etc.)."""
    return transport.patch(f"/discord/events/{pk}/", data)


def create_or_update_signup_message(**data: Any) -> requests.Response | None:
    """Create/update DiscordEventMsgSignup record."""
    return transport.post("/discord/signup-message/", data)


def clear_event_signup_state(event_id: int) -> requests.Response | None:
    """Reset signup dedup state for an event (auto-recovery + manual repost).

    Flips DiscordEventMsgSignup.has_posted=False AND DiscordMessageLog.success=False
    for the event_announcement source. The next sync_discord_events run (within
    60s) will treat the event as having no signup post and recreate it.
    """
    return transport.post("/discord/signup-message/clear/", {"event_id": event_id})


def create_or_update_announcement(**data: Any) -> requests.Response | None:
    """Create/update DiscordEventMsgAnnouncement record."""
    return transport.post("/discord/announcement/", data)


def update_scheduled_event(pk: int, **data: Any) -> requests.Response | None:
    """Update ScheduledEvent fields (discord_message_id, next_post_at)."""
    return transport.patch(f"/discord/scheduled-events/{pk}/", data)


def create_event_dm(**data: Any) -> requests.Response | None:
    """Create DiscordEventDM record (crash-safe: create before send)."""
    return transport.post("/discord/event-dm/", data)


def update_event_dm(pk: int, **data: Any) -> requests.Response | None:
    """Update DiscordEventDM delivery status after DM sent."""
    return transport.patch(f"/discord/event-dm/{pk}/", data)


# ---- Sync state ----


def get_sync_discord_state() -> "SyncDiscordStateSchema | None":
    """Get bulk Discord sync state. Returns SyncDiscordStateSchema or None."""

    resp = transport.get("/discord/sync-state/")
    if resp and resp.ok:
        return SyncDiscordStateSchema.model_validate(resp.json())
    return None


def get_discord_event_state(event_id: int) -> "DiscordEventStateSchema | None":
    """Get Discord event state. Returns DiscordEventStateSchema or None."""

    resp = transport.get(f"/discord/event-state/{event_id}/")
    if resp and resp.ok:
        return DiscordEventStateSchema.model_validate(resp.json())
    return None
