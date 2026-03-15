import logging

from celery import shared_task
from django.utils import timezone

from events.models import Event, EventRepeater, EventState
from events.services import finalize_event_tournament, generate_events_for_repeater

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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def auto_start_tournaments(self):
    """Auto-start tournaments for due events. Runs every minute."""
    now = timezone.now()
    events = Event.objects.filter(
        state=EventState.SIGNUPS_OPEN,
        scheduled_at__lte=now,
        auto_start=True,
        roll_call_enabled=False,
        tournament__isnull=False,
        tournament__state="future",
    ).select_related("tournament")

    started = 0
    for event in events:
        try:
            finalize_event_tournament(event)
            event.state = EventState.IN_PROGRESS
            event.save(update_fields=["state", "updated_at"])
            started += 1
        except Exception:
            logger.exception("Failed to auto-start event %s", event.pk)
    return f"Started {started} tournaments"
