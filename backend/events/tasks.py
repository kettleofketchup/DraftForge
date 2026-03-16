import logging

from celery import shared_task
from django.utils import timezone

from events.models import Event, EventRepeater, EventState
from events.services import generate_events_for_repeater

logger = logging.getLogger(__name__)


@shared_task
def generate_upcoming_events():
    """Generate upcoming events for all active repeaters. Runs hourly."""
    repeaters = EventRepeater.objects.filter(is_active=True).select_related(
        "organization",
        "tournament_league",
        "created_by",
    )
    total = 0
    for repeater in repeaters:
        try:
            events = generate_events_for_repeater(repeater)
            total += len(events)
        except Exception:
            logger.exception("Failed to generate events for repeater %s", repeater.pk)
    return f"Generated {total} events from {repeaters.count()} repeaters"


@shared_task
def open_scheduled_signups():
    """Open signups for events where signups_open_at has passed. Runs every minute."""
    now = timezone.now()
    events = Event.objects.filter(
        state=EventState.UPCOMING,
        signups_open_at__isnull=False,
        signups_open_at__lte=now,
    )
    opened = 0
    for event in events:
        try:
            event.transition_state(EventState.SIGNUPS_OPEN)
            opened += 1
            logger.info(
                "Auto-opened signups for event %s (pk=%s)", event.name, event.pk
            )
        except Exception:
            logger.exception("Failed to auto-open signups for event %s", event.pk)
    return f"Opened signups for {opened} events"
