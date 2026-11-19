from datetime import datetime

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, OrgLog
from events.capacity import lock_event
from events.models import Event
from org.conduct.constants import AUTOMATIC_SOURCES
from org.models_conduct import AttendanceOutcome
from telemetry.logging import get_logger

log = get_logger(__name__)


@transaction.atomic
def void_event_outcomes(
    event: Event, *, now: datetime, actor: CustomUser | None
) -> int:
    locked = lock_event(event)
    claimed = (
        Event.objects.nocache()
        .filter(pk=locked.pk, conduct_finalized_at__isnull=True)
        .update(conduct_finalized_at=now)
    )
    if not claimed:
        return 0
    voided = (
        AttendanceOutcome.objects.nocache()
        .filter(event=locked)
        .update(voided_at=now, updated_at=now)
    )
    if actor is not None:
        OrgLog.objects.create(
            organization_id=locked.organization_id,
            actor=actor,
            action="void_attendance",
            details={"event_id": locked.pk, "voided": voided},
        )
    invalidate_after_commit(locked)
    log.info(
        "conduct_event_voided",
        system="org",
        subsystem="conduct",
        org_id=locked.organization_id,
        event_id=locked.pk,
        actor_id=actor.pk if actor is not None else None,
        voided=voided,
    )
    return voided


@transaction.atomic
def reopen_event_outcomes(event: Event) -> tuple[int, int]:
    rows = AttendanceOutcome.objects.nocache().filter(event_id=event.pk)
    deleted, _ = rows.filter(source__in=AUTOMATIC_SOURCES).delete()
    kept = rows.exclude(source__in=AUTOMATIC_SOURCES).update(
        finalized_at=None, voided_at=None, updated_at=timezone.now()
    )
    log.info(
        "conduct_event_reopened",
        system="org",
        subsystem="conduct",
        org_id=event.organization_id,
        event_id=event.pk,
        deleted=deleted,
        kept=kept,
    )
    return deleted, kept
