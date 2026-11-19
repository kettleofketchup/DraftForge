from django.db import connection
from django.db.models import Count, Q, QuerySet

from events.constants import SEAT_HOLDING_STATUSES, SignupStatus
from events.models import Event, EventSignup


def seat_holding_statuses(event: Event) -> frozenset[str]:
    return SEAT_HOLDING_STATUSES


def count_seats(event: Event) -> int:
    return (
        EventSignup.objects.nocache()
        .filter(event=event, status__in=seat_holding_statuses(event))
        .count()
    )


def with_signup_counts(qs: QuerySet[Event]) -> QuerySet[Event]:
    # One SQL filter for every row: when seat_holding_statuses becomes per-event,
    # this must follow it (SeatCountSurfacesTests guards parity with count_seats).
    return qs.annotate(
        signup_count=Count(
            "signups", filter=Q(signups__status__in=SEAT_HOLDING_STATUSES)
        ),
        confirmed_count=Count(
            "signups", filter=Q(signups__status=SignupStatus.CONFIRMED)
        ),
    )


def free_seats(event: Event) -> int | None:
    """Seats left under max_players; None when capacity is unlimited (unset or 0)."""
    if not event.max_players:
        return None
    return max(0, event.max_players - count_seats(event))


def has_free_seat(event: Event) -> bool:
    free = free_seats(event)
    return free is None or free > 0


def lock_event(event: Event) -> Event:
    """Re-read the event row under a write lock; capacity decisions use the result."""
    assert connection.in_atomic_block, "lock_event requires an atomic block"
    return Event.objects.select_for_update().nocache().get(pk=event.pk)
