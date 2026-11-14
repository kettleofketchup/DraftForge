import copy
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, OrgLog
from events.constants import EVENT_STATE_TRANSITIONS, EventState
from events.models import Event
from org.contributions.services import SyncResult, sync_event_staff_entries
from telemetry.logging import get_logger

log = get_logger(__name__)

CloseSource = Literal["admin", "auto"]

_CLOSE_STATES: frozenset[EventState] = frozenset(
    {EventState.COMPLETED, EventState.CANCELLED}
)


@dataclass(frozen=True)
class CloseResult:
    closed: bool
    state: str


def _should_award(event: Event, new_state: EventState, source: CloseSource) -> bool:
    if new_state == EventState.COMPLETED:
        return True
    if source != "auto" or new_state != EventState.CANCELLED:
        return False
    return event.host_id is not None or event.helpers.nocache().exists()


def close_event(
    event: Event,
    *,
    new_state: EventState,
    source: CloseSource,
    actor: CustomUser | None = None,
    expected_from: Collection[str] | None = None,
) -> CloseResult:
    new_state = EventState(new_state)
    if new_state not in _CLOSE_STATES:
        raise ValueError(f"close_event cannot move an event to {new_state.value!r}")
    allowed_from = [
        state
        for state, nexts in EVENT_STATE_TRANSITIONS.items()
        if new_state in nexts and (expected_from is None or state in expected_from)
    ]
    with transaction.atomic():
        now = timezone.now()
        current = (
            Event.objects.nocache()
            .filter(pk=event.pk)
            .values_list("state", flat=True)
            .first()
        ) or event.state
        changed = current in allowed_from and Event.objects.nocache().filter(
            pk=event.pk, state=current
        ).update(state=new_state, updated_at=now)
        if not changed:
            current = (
                Event.objects.nocache()
                .filter(pk=event.pk)
                .values_list("state", flat=True)
                .first()
            ) or current
            log.info(
                "event_close_skipped",
                system="events",
                subsystem="services",
                event_id=event.pk,
                org_id=event.organization_id,
                source=source,
                new_state=new_state.value,
                current_state=current,
            )
            return CloseResult(closed=False, state=current)

        old_state = current
        stale = copy.copy(event)
        event.refresh_from_db(from_queryset=Event.objects.nocache().all())

        sync: SyncResult | None = None
        if _should_award(event, new_state, source):
            sync = sync_event_staff_entries(event)
            Event.objects.nocache().filter(pk=event.pk).update(
                contributions_awarded_at=now
            )
            event.contributions_awarded_at = now

        if source == "admin" and new_state == EventState.COMPLETED:
            OrgLog.objects.create(
                organization_id=event.organization_id,
                actor=actor,
                action="complete_event",
                details={
                    "event_id": event.pk,
                    "from": old_state,
                    "to": new_state.value,
                    "awarded": sync.created if sync is not None else 0,
                },
            )
        invalidate_after_commit(stale, event)

    log.info(
        "event_closed",
        system="events",
        subsystem="services",
        event_id=event.pk,
        org_id=event.organization_id,
        source=source,
        from_state=old_state,
        new_state=new_state.value,
        awarded=sync is not None,
        created=sync.created if sync is not None else 0,
        actor_id=actor.pk if actor is not None else None,
    )
    return CloseResult(closed=True, state=new_state.value)
