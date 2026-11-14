"""Which tournaments currently accept user signups through their source event."""

from events.constants import EventState
from events.models import Event


def user_signups_open_tournament_ids() -> set[int]:
    """Tournament ids whose source event is SIGNUPS_OPEN.

    Matches the only rule the signup paths enforce (process_rsvp,
    create_tentative_signup, the signup view and the Discord handlers).
    """
    return set(
        Event.objects.filter(state=EventState.SIGNUPS_OPEN, tournament__isnull=False)
        .nocache()
        .values_list("tournament_id", flat=True)
    )
