from django.db import connection

from events.constants import SEAT_HOLDING_STATUSES
from events.models import Event, EventSignup


def seat_holding_statuses(event: Event) -> frozenset[str]:
    return SEAT_HOLDING_STATUSES


def count_seats(event: Event) -> int:
    return (
        EventSignup.objects.nocache()
        .filter(event=event, status__in=seat_holding_statuses(event))
        .count()
    )


def has_free_seat(event: Event) -> bool:
    return not event.max_players or count_seats(event) < event.max_players


def lock_event(event: Event) -> Event:
    """Re-read the event row under a write lock; capacity decisions use the result."""
    assert connection.in_atomic_block, "lock_event requires an atomic block"
    return Event.objects.select_for_update().nocache().get(pk=event.pk)
