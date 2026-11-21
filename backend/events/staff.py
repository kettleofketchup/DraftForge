from django.db import transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from events.models import Event
from org.standing import api as standing
from telemetry.logging import get_logger

log = get_logger(__name__)

_HELPERS = frozenset({"helpers"})


@transaction.atomic
def dedupe_host_helpers(user: CustomUser) -> list[Event]:
    events = list(
        Event.objects.nocache()
        .select_for_update(of=("self",))
        .filter(
            pk__in=Event.objects.nocache().filter(host=user, helpers=user).values("pk")
        )
        .select_related("organization")
    )
    if not events:
        return []
    counts: dict[str, int] = {}
    for event in events:
        event.helpers.remove(user)
        result = standing.on_event_changed(event, fields=_HELPERS)
        for key, value in result.log_fields().items():
            counts[key] = counts.get(key, 0) + int(value)
    invalidate_after_commit(*events)
    log.info(
        "event_staff_deduped",
        system="events",
        subsystem="services",
        user_id=user.pk,
        event_ids=[event.pk for event in events],
        **counts,
    )
    return events
