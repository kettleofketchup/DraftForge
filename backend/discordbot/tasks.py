# backend/discordbot/tasks.py
"""Celery tasks for Discord bot scheduled operations."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import ScheduledEvent
from .utils import sync_add_reactions, sync_send_templated_embed

log = logging.getLogger(__name__)


@shared_task
def check_scheduled_events():
    """
    Check for and post scheduled events that are due.
    Runs every 60 seconds via Celery beat.

    DB writes go through internal HTTP API — no direct ORM writes.
    """
    from app.internal_client import update_scheduled_event

    now = timezone.now()

    due_events = ScheduledEvent.objects.filter(
        is_active=True,
        next_post_at__lte=now,
        discord_message_id__isnull=True,  # Not yet posted
    ).select_related("template")

    for scheduled_event in due_events:
        template = scheduled_event.template

        log.info(f"Posting scheduled event: {template.name}")

        # Send the announcement message (DiscordMessageLog written via HTTP in helper)
        response = sync_send_templated_embed(template)

        if response and "id" in response:
            message_id = response["id"]

            # Add RSVP reactions if enabled
            if template.include_rsvp:
                sync_add_reactions(template.channel_id, message_id)

            log.info(f"Posted event {template.name}, message_id={message_id}")
        else:
            log.error(f"Failed to post event {template.name}")
            continue

        # Update via internal API
        if scheduled_event.is_recurring:
            next_post = (scheduled_event.next_post_at + timedelta(days=7)).isoformat()
            update_scheduled_event(
                scheduled_event.pk,
                discord_message_id=None,  # Reset for next posting
                next_post_at=next_post,
            )
            log.info(f"Rescheduled recurring event {template.name} to {next_post}")
        else:
            update_scheduled_event(
                scheduled_event.pk,
                discord_message_id=message_id,
            )

    return f"Processed {due_events.count()} scheduled events"
