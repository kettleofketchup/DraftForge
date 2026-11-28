import copy
from collections.abc import Mapping
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

import events.eligibility.store  # noqa: F401
from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from events.constants import EVENT_REOPEN_TRANSITIONS, EventState
from events.models import Event
from org.models import OrgLog
from org.standing import api as standing
from telemetry.logging import get_logger

log = get_logger(__name__)

REOPEN_TARGET = EventState.SIGNUPS_OPEN


class ReopenNotPermitted(Exception):
    pass


@dataclass(frozen=True)
class ReopenResult:
    reopened: bool
    state: str
    details: Mapping[str, standing.LogValue] = field(default_factory=dict)


def _current_state(event: Event) -> str:
    return (
        Event.objects.nocache()
        .filter(pk=event.pk)
        .values_list("state", flat=True)
        .first()
    ) or event.state


def reopen_event(event: Event, *, actor: CustomUser | None) -> ReopenResult:
    """Move a closed event back to signups and take back its staff points.

    Promo and manual entries stay; a later close awards staff points again.
    """
    reopen_from = [
        state
        for state, nexts in EVENT_REOPEN_TRANSITIONS.items()
        if REOPEN_TARGET in nexts
    ]
    with transaction.atomic():
        now = timezone.now()
        current = _current_state(event)
        changed = current in reopen_from and Event.objects.nocache().filter(
            pk=event.pk, state=current
        ).update(
            state=REOPEN_TARGET,
            leadership_review_dm_dispatch={},
            **standing.reopen_reset_fields(),
            updated_at=now,
        )
        if not changed:
            current = _current_state(event)
            log.info(
                "event_reopen_skipped",
                system="events",
                subsystem="services",
                event_id=event.pk,
                org_id=event.organization_id,
                current_state=current,
                actor_id=actor.pk if actor is not None else None,
            )
            return ReopenResult(reopened=False, state=current)

        stale = copy.copy(event)
        event.refresh_from_db(from_queryset=Event.objects.nocache().all())
        result = standing.on_event_reopened(event, actor=actor, now=now)
        details = result.orglog_details()
        OrgLog.objects.create(
            organization_id=event.organization_id,
            actor=actor,
            action="reopen_event",
            details={
                "event_id": event.pk,
                "from": current,
                "to": REOPEN_TARGET.value,
                **details,
            },
        )
        invalidate_after_commit(stale, event)
        event.refresh_signup_post_on_commit()

    log.info(
        "event_reopened",
        system="events",
        subsystem="services",
        event_id=event.pk,
        org_id=event.organization_id,
        from_state=current,
        new_state=REOPEN_TARGET.value,
        **result.log_fields(),
        actor_id=actor.pk if actor is not None else None,
    )
    return ReopenResult(reopened=True, state=REOPEN_TARGET.value, details=details)
