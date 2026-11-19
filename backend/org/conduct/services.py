from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from app.models import CustomUser, OrgLog
from events.capacity import lock_event
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from org.conduct.constants import (
    EDITABLE_STATES,
    REASON_MAX_LENGTH,
    REASON_MIN_LENGTH,
    STAFF_SETTABLE,
    Outcome,
    OutcomeSource,
    expected_statuses,
)
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from telemetry.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class SetResult:
    changed: int
    unchanged: int


@dataclass(frozen=True)
class _Planned:
    org_user: OrgUser
    outcome: Outcome
    row: AttendanceOutcome | None
    signup: EventSignup | None


def _validate_request(
    event: Event, changes: list[tuple[OrgUser, Outcome]], reason: str
) -> str:
    if not org_has_feature(event.organization_id, FeatureKey.CONDUCT):
        raise ValueError("Conduct is not enabled for this organization.")
    cleaned = reason.strip()
    if len(cleaned) < REASON_MIN_LENGTH:
        raise ValueError(f"Reason must be at least {REASON_MIN_LENGTH} characters.")
    if len(cleaned) > REASON_MAX_LENGTH:
        raise ValueError(f"Reason must be at most {REASON_MAX_LENGTH} characters.")
    if not changes:
        raise ValueError("No attendance changes were given.")
    seen: set[int] = set()
    for org_user, outcome in changes:
        if org_user.pk in seen:
            raise ValueError("A member appears more than once in the changes.")
        seen.add(org_user.pk)
        if org_user.organization_id != event.organization_id:
            raise ValueError("A member is not part of this organization.")
        if outcome not in STAFF_SETTABLE:
            raise ValueError(f"Outcome {outcome!r} cannot be set by staff.")
    return cleaned


def _validate_state(locked: Event) -> None:
    if locked.state == EventState.CANCELLED:
        raise ValueError(
            "This event was cancelled. Reopen and complete it to record attendance."
        )
    if locked.state == EventState.COMPLETED:
        if locked.conduct_finalized_at is None:
            raise ValueError("Attendance was not tracked for this event.")
        return
    if locked.state not in EDITABLE_STATES:
        raise ValueError("Attendance can only be recorded from roll call onwards.")


def _plan(locked: Event, changes: list[tuple[OrgUser, Outcome]]) -> list[_Planned]:
    org_user_ids = [org_user.pk for org_user, _ in changes]
    user_ids = [org_user.user_id for org_user, _ in changes]
    rows = {
        row.org_user_id: row
        for row in AttendanceOutcome.objects.nocache().filter(
            event_id=locked.pk, org_user_id__in=org_user_ids
        )
    }
    signups = {
        s.user_id: s
        for s in EventSignup.objects.nocache().filter(
            event_id=locked.pk, user_id__in=user_ids
        )
    }
    expected = expected_statuses(locked) | {SignupStatus.DROPPED}
    planned: list[_Planned] = []
    for org_user, outcome in changes:
        row = rows.get(org_user.pk)
        signup = signups.get(org_user.user_id)
        if signup is not None and signup.status not in expected:
            signup = None
        if row is None and signup is None and outcome != Outcome.ATTENDED:
            raise ValueError(
                "Only Attended can be recorded for a member who was not signed up."
            )
        planned.append(
            _Planned(org_user=org_user, outcome=outcome, row=row, signup=signup)
        )
    return planned


def _apply(
    locked: Event,
    item: _Planned,
    *,
    actor: CustomUser,
    reason: str,
    now: datetime,
) -> AttendanceOutcome | None:
    row = item.row
    finalize = locked.conduct_finalized_at is not None
    if row is None:
        return AttendanceOutcome.objects.create(
            organization_id=locked.organization_id,
            org_user=item.org_user,
            event=locked,
            event_name=locked.name,
            event_starts_at=locked.scheduled_at,
            signup=item.signup,
            committed=item.signup is not None,
            outcome=item.outcome,
            source=OutcomeSource.STAFF,
            set_by=actor,
            reason=reason,
            finalized_at=now if finalize else None,
        )
    if row.outcome == item.outcome and row.source == OutcomeSource.STAFF:
        return None
    row.outcome = item.outcome
    row.source = OutcomeSource.STAFF
    row.set_by = actor
    row.reason = reason
    if finalize and row.finalized_at is None:
        row.finalized_at = now
    row.save(
        update_fields=[
            "outcome",
            "source",
            "set_by",
            "reason",
            "finalized_at",
            "updated_at",
        ]
    )
    return row


@transaction.atomic
def set_outcomes(
    event: Event,
    *,
    actor: CustomUser,
    changes: list[tuple[OrgUser, Outcome]],
    reason: str,
) -> SetResult:
    cleaned = _validate_request(event, changes, reason)
    locked = lock_event(event)
    _validate_state(locked)
    planned = _plan(locked, changes)
    now = timezone.now()
    changed = 0
    for item in planned:
        old = (
            {"outcome": item.row.outcome, "source": item.row.source}
            if item.row is not None
            else {
                "outcome": Outcome.PENDING.value,
                "source": OutcomeSource.DEFAULT.value,
            }
        )
        row = _apply(locked, item, actor=actor, reason=cleaned, now=now)
        if row is None:
            continue
        changed += 1
        OrgLog.objects.create(
            organization_id=locked.organization_id,
            actor=actor,
            action="set_attendance",
            details={
                "outcome_pk": row.pk,
                "event_id": locked.pk,
                "org_user_id": item.org_user.pk,
                "old": old,
                "new": {"outcome": row.outcome, "source": row.source},
                "reason": cleaned,
            },
        )
    result = SetResult(changed=changed, unchanged=len(planned) - changed)
    log.info(
        "conduct_outcomes_set",
        system="org",
        subsystem="conduct",
        org_id=locked.organization_id,
        event_id=locked.pk,
        actor_id=actor.pk,
        changed=result.changed,
        unchanged=result.unchanged,
        finalized=locked.conduct_finalized_at is not None,
    )
    return result


@transaction.atomic
def reassign_member(drop: OrgUser, keep: OrgUser) -> int:
    if drop.organization_id != keep.organization_id:
        raise ValueError("cannot reassign conduct across organizations")
    if drop.pk == keep.pk:
        return 0
    rows = AttendanceOutcome.objects.nocache()
    keep_rows = {
        event_id: source
        for event_id, source in rows.filter(
            org_user=keep, event__isnull=False
        ).values_list("event_id", "source")
    }
    discard_drop: list[int] = []
    discard_keep: list[int] = []
    for pk, event_id, source in rows.filter(org_user=drop).values_list(
        "pk", "event_id", "source"
    ):
        if event_id is None or event_id not in keep_rows:
            continue
        drop_staff = source == OutcomeSource.STAFF
        keep_staff = keep_rows[event_id] == OutcomeSource.STAFF
        if drop_staff and not keep_staff:
            discard_keep.append(event_id)
        else:
            discard_drop.append(pk)
    rows.filter(org_user=keep, event_id__in=discard_keep).delete()
    rows.filter(pk__in=discard_drop).delete()
    moved = rows.filter(org_user=drop).update(org_user=keep, updated_at=timezone.now())
    log.info(
        "conduct_member_reassigned",
        system="org",
        subsystem="conduct",
        org_id=keep.organization_id,
        drop_org_user_id=drop.pk,
        keep_org_user_id=keep.pk,
        moved=moved,
        discarded=len(discard_drop) + len(discard_keep),
    )
    return moved
