"""
Dispatch functions — check config flags and call .delay().

IMPORTANT: These dispatch functions call .delay() which publishes to Redis
immediately. When called from inside @transaction.atomic services, the caller
MUST wrap in transaction.on_commit() to ensure data is committed before the
Celery worker reads it.

Exception: generate_events_for_repeater() is NOT atomic, so direct calls
are safe there.
"""

import logging

logger = logging.getLogger(__name__)


def notify_event_announced(event):
    """Dispatch announcement task if discord_announcement is enabled."""
    if event.discord_announcement and event.discord_announcement_channel_id:
        from events.tasks import send_event_announcement

        send_event_announcement.delay(event.pk)


def notify_signup_changed(event):
    """Dispatch signup update task to edit the announcement embed."""
    if event.discord_announcement and event.discord_announcement_channel_id:
        from events.tasks import send_signup_update

        send_signup_update.delay(event.pk)


def notify_new_event(event):
    """Dispatch new event notification if discord_announcement is enabled."""
    if event.discord_announcement and event.discord_announcement_channel_id:
        from events.tasks import send_new_event_notification

        send_new_event_notification.delay(event.pk)


def notify_create_discord_event(event):
    """Dispatch Discord scheduled event creation if enabled."""
    if event.discord_create_event:
        from events.tasks import create_discord_scheduled_event

        create_discord_scheduled_event.delay(event.pk)


def notify_sync_signups(event):
    """Dispatch Discord event signup sync if enabled."""
    if event.discord_sync_signups:
        from events.tasks import sync_discord_event_signups

        sync_discord_event_signups.delay(event.pk)


def notify_mark_interested(event, user_id):
    """Dispatch Discord 'mark interested' if enabled."""
    if event.discord_mark_interested:
        from events.tasks import mark_interested_discord_event

        mark_interested_discord_event.delay(event.pk, user_id)
