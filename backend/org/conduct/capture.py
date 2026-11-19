from datetime import datetime, timedelta

from django.db import transaction

from events.capacity import lock_event
from events.models import EventSignup
from org.conduct.constants import (
    PRE_CLOSE_STATES,
    Outcome,
    OutcomeSource,
    expected_statuses,
)
from org.conduct.gate import get_conduct_settings
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from telemetry.logging import get_logger

log = get_logger(__name__)


@transaction.atomic
def capture_late_cancel(
    signup: EventSignup, *, prior_status: str, now: datetime
) -> AttendanceOutcome | None:
    locked = lock_event(signup.event)
    org_id = locked.organization_id
    if not org_has_feature(org_id, FeatureKey.CONDUCT):
        return None

    def ignored(reason: str) -> None:
        log.debug(
            "conduct_late_cancel_ignored",
            system="org",
            subsystem="conduct",
            org_id=org_id,
            event_id=locked.pk,
            user_id=signup.user_id,
            reason=reason,
        )

    if locked.state not in PRE_CLOSE_STATES:
        ignored("closed")
        return None
    if locked.conduct_finalized_at is not None:
        ignored("finalized")
        return None
    if prior_status not in expected_statuses(locked):
        ignored("not_expected")
        return None

    starts_at = locked.scheduled_at
    if now >= starts_at:
        outcome = Outcome.NO_SHOW
    else:
        hours = get_conduct_settings(org_id).late_cancel_hours
        if hours <= 0 or now < starts_at - timedelta(hours=hours):
            ignored("outside_window")
            return None
        outcome = Outcome.LATE_CANCEL

    org_user, _ = OrgUser.objects.nocache().get_or_create(
        user_id=signup.user_id, organization_id=org_id
    )
    existing = (
        AttendanceOutcome.objects.nocache()
        .filter(event=locked, org_user=org_user)
        .first()
    )
    if existing is not None and existing.finalized_at is not None:
        ignored("finalized")
        return None
    if existing is not None and existing.source == OutcomeSource.STAFF:
        ignored("staff_row")
        return None

    row, _ = AttendanceOutcome.objects.nocache().update_or_create(
        event=locked,
        org_user=org_user,
        defaults={
            "organization_id": org_id,
            "event_name": locked.name,
            "event_starts_at": starts_at,
            "signup": signup,
            "outcome": outcome,
            "source": OutcomeSource.LATE_CANCEL,
            "cancelled_at": now,
            "committed": True,
        },
    )
    log.info(
        "conduct_late_cancel_captured",
        system="org",
        subsystem="conduct",
        org_id=org_id,
        event_id=locked.pk,
        org_user_id=org_user.pk,
        user_id=signup.user_id,
        outcome=str(outcome),
        hours_before_start=round((starts_at - now).total_seconds() / 3600, 2),
    )
    return row
