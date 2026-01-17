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
    """
    now = timezone.now()

    due_events = ScheduledEvent.objects.filter(
        is_active=True,
        next_post_at__lte=now,
        discord_message_id__isnull=True,  # Not yet posted
    ).select_related("template")

    for scheduled_event in due_events:
        template = scheduled_event.template

        log.info(f"Posting scheduled event: {template.name}")

        # Send the announcement message
        response = sync_send_templated_embed(template)

        if response and "id" in response:
            message_id = response["id"]
            scheduled_event.discord_message_id = message_id

            # Add RSVP reactions if enabled
            if template.include_rsvp:
                sync_add_reactions(template.channel_id, message_id)

            log.info(f"Posted event {template.name}, message_id={message_id}")
        else:
            log.error(f"Failed to post event {template.name}")
            continue

        # Handle recurring events
        if scheduled_event.is_recurring:
            # Schedule next occurrence (7 days later)
            scheduled_event.next_post_at = scheduled_event.next_post_at + timedelta(
                days=7
            )
            scheduled_event.discord_message_id = None  # Reset for next posting
            log.info(
                f"Rescheduled recurring event {template.name} to {scheduled_event.next_post_at}"
            )

        scheduled_event.save()

    return f"Processed {due_events.count()} scheduled events"
