from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from org.models import (
    OrgApiConnection,
    OrgApiMmrPullTarget,
    OrgApiSyncRun,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

ACTIVE_STATES = ("queued", "running", "partial")
LEASE_SECONDS = 60
ISSUE_EXAMPLES = 100
COUNTERS = (
    "request_count",
    "row_count",
    "updated_count",
    "unchanged_count",
    "unmatched_count",
    "invalid_count",
    "conflict_count",
    "skipped_policy_count",
    "missing_identifier_count",
    "verified_count",
    "issue_count",
)


def acquire_lease(run_id: UUID, *, now: datetime | None = None) -> UUID | None:
    now = now or timezone.now()
    fence = uuid4()
    claimed = (
        OrgApiSyncRun.objects.filter(pk=run_id, state__in=ACTIVE_STATES)
        .filter(Q(lease_token__isnull=True) | Q(lease_expires_at__lte=now))
        .update(
            lease_token=fence, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS)
        )
    )
    return fence if claimed else None


def fenced_runs(run_id: UUID, fence: UUID) -> QuerySet[OrgApiSyncRun]:
    return OrgApiSyncRun.objects.filter(
        pk=run_id,
        lease_token=fence,
        lease_expires_at__gt=timezone.now(),
        state__in=ACTIVE_STATES,
    )


def holds_fence(run: OrgApiSyncRun, fence: UUID) -> bool:
    return (
        run.state in ACTIVE_STATES
        and run.lease_token == fence
        and run.lease_expires_at is not None
        and run.lease_expires_at > timezone.now()
    )


def lock_fenced_run(run_id: UUID, fence: UUID) -> OrgApiSyncRun | None:
    return fenced_runs(run_id, fence).select_for_update().first()


def renew_lease(run: OrgApiSyncRun) -> None:
    run.lease_expires_at = timezone.now() + timedelta(seconds=LEASE_SECONDS)


def add_issues(run: OrgApiSyncRun, issues: list[dict[str, Any]]) -> None:
    run.issue_count += len(issues)
    room = ISSUE_EXAMPLES - len(run.issues)
    if room > 0:
        run.issues = [*run.issues, *issues[:room]]


def run_summary(run: OrgApiSyncRun) -> dict[str, Any]:
    return {
        "run_id": str(run.pk),
        "kind": run.kind,
        "state": run.state,
        "error_code": run.error_code,
        **{field: getattr(run, field) for field in COUNTERS},
    }


def finish_run(
    run_id: UUID, fence: UUID, *, state: str, error_code: str = ""
) -> OrgApiSyncRun | None:
    now = timezone.now()
    with transaction.atomic():
        run = lock_fenced_run(run_id, fence)
        if run is None:
            return None
        run.state = state
        run.error_code = error_code
        run.finished_at = now
        run.lease_token = None
        run.lease_expires_at = None
        run.save(
            update_fields=[
                "state",
                "error_code",
                "finished_at",
                "lease_token",
                "lease_expires_at",
            ]
        )
        if state != OrgApiSyncRun.State.SUCCEEDED:
            OrgApiMmrPullTarget.objects.filter(run=run, outcome_code="").delete()
        updates: dict[str, Any] = {
            "last_run_summary": run_summary(run),
            "last_error_code": error_code,
        }
        if state == OrgApiSyncRun.State.SUCCEEDED:
            updates["last_success_at"] = now
        OrgApiConnection.objects.filter(pk=run.connection_id).update(**updates)
    log.info(
        "api_connection_run_finished",
        system="org",
        subsystem="api_connections",
        org_id=run.organization_id,
        connection_id=run.connection_id,
        run_id=str(run.pk),
        kind=run.kind,
        state=state,
        error_code=error_code or None,
        **{field: getattr(run, field) for field in COUNTERS},
    )
    return run
