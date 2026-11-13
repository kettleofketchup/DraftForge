"""Which tournaments currently accept user signups through their source event."""

from datetime import datetime, timedelta

from django.db.models import Q

from events.constants import EventState
from events.models import Event


def user_signups_open_tournament_ids(now: datetime) -> set[int]:
    """Tournament ids whose source event takes user signups at ``now``.

    Signups are open while the event is SIGNUPS_OPEN (the state process_rsvp
    requires), user signups are allowed, ``signups_open_at`` has passed and the
    ``signup_deadline_hours`` cutoff before ``scheduled_at`` has not.
    """
    rows = (
        Event.objects.filter(
            Q(signups_open_at__isnull=True) | Q(signups_open_at__lte=now),
            state=EventState.SIGNUPS_OPEN,
            allow_user_signups=True,
            tournament__isnull=False,
        )
        .nocache()
        .values_list("tournament_id", "scheduled_at", "signup_deadline_hours")
    )
    return {
        tournament_id
        for tournament_id, scheduled_at, deadline_hours in rows
        if deadline_hours is None
        or now < scheduled_at - timedelta(hours=deadline_hours)
    }
