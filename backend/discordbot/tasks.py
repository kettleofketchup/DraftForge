# backend/discordbot/tasks.py
"""Celery tasks for Discord bot scheduled operations."""

import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

from .utils import sync_add_reactions, sync_send_embed

log = logging.getLogger(__name__)


@shared_task
def check_scheduled_events():
    """
    Check for and post scheduled events that are due.
    Runs every 60 seconds via Celery beat.

    All reads via internal HTTP API. Embeds built from template data.
    """
    from app.internal_client import get_due_scheduled_events, update_scheduled_event

    due_events = get_due_scheduled_events()
    processed = 0

    for se in due_events:
        tpl = se.template
        log.info(f"Posting scheduled event: {tpl.name}")

        # Build embed from template data (same fields as event_announcement_embed)
        color = int(tpl.color.lstrip("#"), 16) if tpl.color else 0x7289DA
        response = sync_send_embed(
            channel_id=tpl.channel_id,
            title=tpl.title,
            description=tpl.description,
            color=color,
            footer=(
                {"text": "React: \u2705 Yes | \u2753 Maybe | \u274c No"}
                if tpl.include_rsvp
                else None
            ),
            source="scheduled_event",
            source_id=se.pk,
        )

        if response and "id" in response:
            message_id = response["id"]

            if tpl.include_rsvp:
                sync_add_reactions(tpl.channel_id, message_id)

            log.info(f"Posted event {tpl.name}, message_id={message_id}")
        else:
            log.error(f"Failed to post event {tpl.name}")
            continue

        # Update via internal API
        if se.is_recurring and se.next_post_at:
            dt = datetime.fromisoformat(se.next_post_at) + timedelta(days=7)
            update_scheduled_event(
                se.pk,
                discord_message_id=None,
                next_post_at=dt.isoformat(),
            )
            log.info(f"Rescheduled recurring event {tpl.name} to {dt.isoformat()}")
        else:
            update_scheduled_event(se.pk, discord_message_id=message_id)
        processed += 1

    return f"Processed {processed} scheduled events"
