"""
Dispatch functions — check config flags and call .delay().

IMPORTANT: These dispatch functions call .delay() which publishes to Redis
immediately. When called from inside @transaction.atomic services, the caller
MUST wrap in transaction.on_commit() to ensure data is committed before the
Celery worker reads it.

Exception: generate_events_for_repeater() is NOT atomic, so direct calls
are safe there.
"""

from structlog.contextvars import get_contextvars

from telemetry.logging import get_logger

log = get_logger(__name__)


def _current_interaction_id() -> str | None:
    """Read interaction_id from contextvars (set by discord_log_context)."""
    return get_contextvars().get("interaction_id")


def _log_skipped(event, reason: str, task: str) -> None:
    log.debug(
        "embed_update_skipped",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=event.pk,
        task=task,
        reason=reason,
    )


def _log_queued(event, task: str) -> None:
    log.info(
        "embed_update_queued",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=event.pk,
        task=task,
    )


def notify_event_announced(event):
    """Dispatch announcement task if discord_announcement is enabled."""
    if not event.discord_announcement:
        _log_skipped(event, "discord_announcement_disabled", "send_event_announcement")
        return
    if not event.discord_announcement_channel_id:
        _log_skipped(event, "no_channel_id", "send_event_announcement")
        return
    from events.tasks import send_event_announcement

    interaction_id = _current_interaction_id()
    send_event_announcement.delay(event.pk, interaction_id=interaction_id)
    _log_queued(event, "send_event_announcement")


def notify_signup_changed(event):
    """Dispatch signup update task to edit the announcement embed."""
    if not event.discord_announcement:
        _log_skipped(event, "discord_announcement_disabled", "send_signup_update")
        return
    if not event.discord_announcement_channel_id:
        _log_skipped(event, "no_channel_id", "send_signup_update")
        return
    from events.tasks import send_signup_update

    interaction_id = _current_interaction_id()
    send_signup_update.delay(event.pk, interaction_id=interaction_id)
    _log_queued(event, "send_signup_update")


def notify_new_event(event):
    """Dispatch new event notification if discord_announcement is enabled."""
    if not event.discord_announcement:
        _log_skipped(event, "discord_announcement_disabled", "send_new_event_notification")
        return
    if not event.discord_announcement_channel_id:
        _log_skipped(event, "no_channel_id", "send_new_event_notification")
        return
    from events.tasks import send_new_event_notification

    interaction_id = _current_interaction_id()
    send_new_event_notification.delay(event.pk, interaction_id=interaction_id)
    _log_queued(event, "send_new_event_notification")


def notify_create_discord_event(event):
    """Dispatch Discord scheduled event creation if enabled."""
    if not event.discord_create_event:
        _log_skipped(event, "discord_create_event_disabled", "create_discord_scheduled_event")
        return
    from events.tasks import create_discord_scheduled_event

    interaction_id = _current_interaction_id()
    create_discord_scheduled_event.delay(event.pk, interaction_id=interaction_id)
    _log_queued(event, "create_discord_scheduled_event")


def notify_sync_signups(event):
    """Dispatch Discord event signup sync if enabled."""
    if not event.discord_sync_signups:
        _log_skipped(event, "discord_sync_signups_disabled", "sync_discord_event_signups")
        return
    from events.tasks import sync_discord_event_signups

    interaction_id = _current_interaction_id()
    sync_discord_event_signups.delay(event.pk, interaction_id=interaction_id)
    _log_queued(event, "sync_discord_event_signups")


def notify_mark_interested(event, user_id):
    """Dispatch Discord 'mark interested' if enabled."""
    if not event.discord_mark_interested:
        _log_skipped(event, "discord_mark_interested_disabled", "mark_interested_discord_event")
        return
    from events.tasks import mark_interested_discord_event

    interaction_id = _current_interaction_id()
    mark_interested_discord_event.delay(event.pk, user_id, interaction_id=interaction_id)
    _log_queued(event, "mark_interested_discord_event")
