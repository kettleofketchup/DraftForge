from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, OrgLog
from events.capacity import lock_event
from events.constants import SignupStatus
from events.models import Event, EventSignup, ReadyCheck
from events.services import resolve_or_create_org_user
from org.conduct.constants import Outcome, OutcomeSource, expected_statuses
from org.conduct.gate import get_conduct_settings
from org.conduct.sources import automatic_outcomes, qualifying_ready_check
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from telemetry.logging import get_logger

log = get_logger(__name__)

Resolution = tuple[Outcome, OutcomeSource]

_STAMP_FIELDS: tuple[str, ...] = (
    "finalized_at",
    "signup_status_at_close",
    "event_starts_at",
    "event_name",
    "updated_at",
)


@dataclass(frozen=True)
class FinalizeResult:
    attended: int
    no_show: int
    late_cancel: int
    excused: int
    pending: int
    automatic: int
    materialized: int


def roll_call_pending_user_ids(
    locked: Event, signups: Sequence[EventSignup], check: ReadyCheck | None
) -> set[int]:
    if not locked.roll_call_enabled or check is not None:
        return set()
    if not any(s.status == SignupStatus.CONFIRMED for s in signups):
        return set()
    return {s.user_id for s in signups if s.status == SignupStatus.APPROVED}


def _late_cancel_outcome(
    cancelled_at: datetime, *, starts_at: datetime, hours: int
) -> Outcome | None:
    if cancelled_at >= starts_at:
        return Outcome.NO_SHOW
    if hours > 0 and cancelled_at >= starts_at - timedelta(hours=hours):
        return Outcome.LATE_CANCEL
    return None


def _org_users_for(locked: Event, signups: Sequence[EventSignup]) -> dict[int, OrgUser]:
    user_ids = {s.user_id for s in signups}
    org_users = {
        ou.user_id: ou
        for ou in OrgUser.objects.nocache().filter(
            organization_id=locked.organization_id, user_id__in=user_ids
        )
    }
    for signup in signups:
        if signup.user_id not in org_users:
            org_users[signup.user_id] = resolve_or_create_org_user(
                signup.user, locked.organization
            )
    return org_users


def _materialize(
    locked: Event,
    signups: Sequence[EventSignup],
    rows: dict[int, AttendanceOutcome],
) -> tuple[int, int]:
    expected = expected_statuses(locked)
    targets = [
        s for s in signups if s.status in expected or s.status == SignupStatus.DROPPED
    ]
    org_users = _org_users_for(locked, targets)
    check = qualifying_ready_check(locked)
    auto = automatic_outcomes(locked, org_users, targets)
    pending_users = roll_call_pending_user_ids(locked, signups, check)

    def resolve(signup: EventSignup, org_user: OrgUser) -> Resolution:
        if org_user.pk in auto:
            return auto[org_user.pk]
        if signup.status == SignupStatus.DROPPED or signup.user_id in pending_users:
            return Outcome.PENDING, OutcomeSource.DEFAULT
        return Outcome.ATTENDED, OutcomeSource.DEFAULT

    automatic = 0
    materialized = 0
    handled: set[int] = set()
    for signup in targets:
        org_user = org_users[signup.user_id]
        handled.add(org_user.pk)
        row = rows.get(org_user.pk)
        if row is not None and row.source == OutcomeSource.STAFF:
            continue
        outcome, source = resolve(signup, org_user)
        if source not in (OutcomeSource.DEFAULT, OutcomeSource.LATE_CANCEL):
            automatic += 1
        if row is None:
            rows[org_user.pk] = AttendanceOutcome.objects.create(
                organization_id=locked.organization_id,
                org_user=org_user,
                event=locked,
                event_name=locked.name,
                event_starts_at=locked.scheduled_at,
                signup=signup,
                outcome=outcome,
                source=source,
            )
            materialized += 1
            continue
        row.outcome = outcome
        row.source = source
        row.signup = signup
        row.cancelled_at = None
        row.save(
            update_fields=["outcome", "source", "signup", "cancelled_at", "updated_at"]
        )

    hours = get_conduct_settings(locked.organization_id).late_cancel_hours
    for org_user_id, row in list(rows.items()):
        if org_user_id in handled or row.source != OutcomeSource.LATE_CANCEL:
            continue
        if row.cancelled_at is None:
            continue
        outcome = _late_cancel_outcome(
            row.cancelled_at, starts_at=locked.scheduled_at, hours=hours
        )
        if outcome is None:
            row.delete()
            del rows[org_user_id]
        elif outcome != row.outcome:
            row.outcome = outcome
            row.save(update_fields=["outcome", "updated_at"])
    return automatic, materialized


def _stamp(
    locked: Event,
    signups: Sequence[EventSignup],
    rows: Sequence[AttendanceOutcome],
    *,
    now: datetime,
) -> None:
    status_by_user = {s.user_id: s.status for s in signups}
    for row in rows:
        row.signup_status_at_close = status_by_user.get(
            row.org_user.user_id, row.signup_status_at_close
        )
        row.event_starts_at = locked.scheduled_at
        row.event_name = locked.name
        row.updated_at = now
        if row.outcome != Outcome.PENDING and row.finalized_at is None:
            row.finalized_at = now
    AttendanceOutcome.objects.nocache().bulk_update(rows, _STAMP_FIELDS)


@transaction.atomic
def finalize_event_outcomes(
    event: Event, *, now: datetime, actor: CustomUser | None
) -> FinalizeResult | None:
    locked = lock_event(event)
    claimed = (
        Event.objects.nocache()
        .filter(pk=locked.pk, conduct_finalized_at__isnull=True)
        .update(conduct_finalized_at=now)
    )
    if not claimed:
        return None
    org_id = locked.organization_id
    signups = list(
        EventSignup.objects.nocache().filter(event_id=locked.pk).select_related("user")
    )
    rows = {
        row.org_user_id: row
        for row in AttendanceOutcome.objects.nocache()
        .filter(event_id=locked.pk)
        .select_related("org_user")
    }
    automatic = materialized = 0
    if org_has_feature(org_id, FeatureKey.CONDUCT):
        automatic, materialized = _materialize(locked, signups, rows)
    final_rows = list(
        AttendanceOutcome.objects.nocache()
        .filter(event_id=locked.pk)
        .select_related("org_user")
    )
    _stamp(locked, signups, final_rows, now=now)

    counts = Counter(row.outcome for row in final_rows)
    result = FinalizeResult(
        attended=counts[Outcome.ATTENDED],
        no_show=counts[Outcome.NO_SHOW],
        late_cancel=counts[Outcome.LATE_CANCEL],
        excused=counts[Outcome.EXCUSED],
        pending=counts[Outcome.PENDING],
        automatic=automatic,
        materialized=materialized,
    )
    if actor is not None:
        OrgLog.objects.create(
            organization_id=org_id,
            actor=actor,
            action="finalize_attendance",
            details={
                "event_id": locked.pk,
                "attended": result.attended,
                "no_show": result.no_show,
                "late_cancel": result.late_cancel,
                "excused": result.excused,
                "pending": result.pending,
            },
        )
    invalidate_after_commit(locked)
    log.info(
        "conduct_event_finalized",
        system="org",
        subsystem="conduct",
        org_id=org_id,
        event_id=locked.pk,
        actor_id=actor.pk if actor is not None else None,
        attended=result.attended,
        no_show=result.no_show,
        late_cancel=result.late_cancel,
        excused=result.excused,
        pending=result.pending,
        automatic=result.automatic,
        materialized=result.materialized,
    )
    return result
