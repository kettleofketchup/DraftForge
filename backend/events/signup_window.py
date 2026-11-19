"""Which tournaments currently accept user signups through their source event."""

from events.admission import self_serve_open_q
from events.models import Event


def user_signups_open_tournament_ids() -> set[int]:
    """Tournament ids whose source event admits self-serve signups."""
    return set(
        Event.objects.filter(self_serve_open_q(), tournament__isnull=False)
        .nocache()
        .values_list("tournament_id", flat=True)
    )
