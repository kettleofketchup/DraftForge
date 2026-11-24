"""Send retained outbox receipts to the adaptor, one DM per request.

Run explicitly by ``python manage.py dispatch_promotion_contacts``; there is
no Celery task or schedule. Each row moves through three short steps:

1. ``claim``: a compare-and-set in its own transaction moves a due row to
   ``in_flight`` with a fresh lease token and counts the attempt. Two
   dispatchers can read the same row but only one claim succeeds, on
   SQLite as on PostgreSQL.
2. The frozen payload is sent with no transaction open.
3. ``finalize``: a compare-and-set that only succeeds while the row is still
   ``in_flight`` under that same lease. A late answer for a row that was
   since canceled, re-leased or applied changes nothing.

States after an answer:

- ``applied`` only for a fully validated applied outcome. Terminal.
- ``paused`` for the adaptor's disabled or dry-run answer and for 401/403.
  No retry is scheduled; ``resume_paused=True`` (the command's
  ``--resume-paused``) is the only way back to ``pending``.
- ``reconciliation_required`` for already_contacted, mapping or idempotency
  conflicts, rejected requests, invalid answers, a payload that no longer
  matches its hash and the last allowed failed attempt.
- ``retry`` for timeouts, connection errors, 408, 429 and 5xx, with capped
  exponential backoff that never comes back sooner than Retry-After.

A row whose lease expired (the dispatcher died mid-request) is due again and
is resent with the same delivery UUID and bytes. Rows are dispatched only for
orgs and events bound in ``SFG_PROMOTION_SYNC``; others stay pending.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Protocol

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from config.promotion_sync import PromotionAdaptorConfig
from org.integration.adaptor_client import (
    OutcomeKind,
    PromotionAdaptorClient,
    ReceiptOutcome,
)
from org.integration.receipts import canonical_receipt_hash
from org.models_promotion_sync import OutboxState, PromotionContactOutbox
from telemetry.logging import get_logger

log = get_logger(__name__)

PAYLOAD_INTEGRITY: Final[str] = "payload_integrity"
RETRIES_EXHAUSTED: Final[str] = "retries_exhausted"
DISPATCH_ERROR: Final[str] = "dispatch_error"
BASE_BACKOFF_SECONDS: Final[float] = 5.0
# Retry-After is honored even past the backoff cap, up to this ceiling.
MAX_RETRY_AFTER_SECONDS: Final[float] = 3600.0

_RECONCILE: Final = frozenset(
    {
        OutcomeKind.ALREADY_CONTACTED,
        OutcomeKind.MAPPING_REQUIRED,
        OutcomeKind.IDEMPOTENCY_CONFLICT,
        OutcomeKind.REJECTED,
        OutcomeKind.INVALID_RESPONSE,
    }
)
_PAUSE: Final = frozenset(
    {OutcomeKind.NOT_APPLIED, OutcomeKind.UNAUTHORIZED, OutcomeKind.FORBIDDEN}
)


class ReceiptClient(Protocol):
    def record(self, payload: dict[str, Any]) -> ReceiptOutcome: ...


@dataclass(frozen=True)
class Lease:
    pk: int
    token: uuid.UUID
    attempts: int
    org_id: int
    local_send_id: int
    delivery_id: str
    payload: dict[str, Any]


@dataclass
class DispatchReport:
    enabled: bool
    dry_run: bool = False
    due: int = 0
    resumed: int = 0
    leased: int = 0
    discarded: int = 0
    skipped_unbound: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    reasons: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "due": self.due,
            "resumed": self.resumed,
            "leased": self.leased,
            "discarded": self.discarded,
            "skipped_unbound": self.skipped_unbound,
            "counts": dict(sorted(self.counts.items())),
            "reasons": dict(sorted(self.reasons.items())),
        }


def _config() -> PromotionAdaptorConfig:
    return settings.PROMOTION_ADAPTOR


def _bound() -> Q:
    """Rows whose org and event are both bound to an SFG occasion."""
    q = Q(pk__in=[])
    for binding in settings.SFG_PROMOTION_SYNC.bindings:
        if binding.events:
            q |= Q(organization_id=binding.org_id, event_id__in=list(binding.events))
    return q


def _due(now: datetime) -> Q:
    return Q(state__in=(OutboxState.PENDING, OutboxState.RETRY), due_at__lte=now) | Q(
        state=OutboxState.IN_FLIGHT, lease_expires_at__lte=now
    )


def lease_seconds(config: PromotionAdaptorConfig) -> float:
    return max(2 * config.timeout, config.timeout + 60)


def backoff_seconds(
    attempts: int, retry_after: float | None, config: PromotionAdaptorConfig
) -> float:
    delay = min(config.retry_cap, BASE_BACKOFF_SECONDS * 2 ** max(attempts - 1, 0))
    if retry_after is not None:
        delay = max(delay, min(retry_after, MAX_RETRY_AFTER_SECONDS))
    return delay


def claim(
    row: PromotionContactOutbox, *, now: datetime, config: PromotionAdaptorConfig
) -> Lease | None:
    """Lease ``row`` as read, or None if it changed or must not be sent."""
    current = PromotionContactOutbox.objects.filter(
        _due(now),
        pk=row.pk,
        state=row.state,
        lease_token=row.lease_token,
        attempts=row.attempts,
    )
    with transaction.atomic(durable=True):
        stop = _unsendable_reason(row, config)
        if stop is not None:
            moved = current.update(
                state=OutboxState.RECONCILIATION_REQUIRED,
                last_reason=stop,
                due_at=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
            if moved:
                _log_finished(
                    row, row.attempts, OutboxState.RECONCILIATION_REQUIRED, stop
                )
            return None
        token = uuid.uuid4()
        moved = current.update(
            state=OutboxState.IN_FLIGHT,
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=lease_seconds(config)),
            attempts=F("attempts") + 1,
            updated_at=now,
        )
    if not moved:
        return None
    assert row.payload is not None
    return Lease(
        pk=row.pk,
        token=token,
        attempts=row.attempts + 1,
        org_id=row.organization_id,
        local_send_id=row.local_send_id,
        delivery_id=str(row.delivery_id),
        payload=row.payload,
    )


def _unsendable_reason(
    row: PromotionContactOutbox, config: PromotionAdaptorConfig
) -> str | None:
    if (
        row.payload is None
        or not row.payload_hash
        or canonical_receipt_hash(row.payload) != row.payload_hash
        or row.payload.get("delivery_id") != str(row.delivery_id)
        or row.payload.get("org_id") != str(row.organization_id)
    ):
        return PAYLOAD_INTEGRITY
    if row.state == OutboxState.IN_FLIGHT and row.attempts >= config.max_attempts:
        # The last allowed attempt was abandoned mid-request.
        return RETRIES_EXHAUSTED
    return None


def _next_state(
    lease: Lease, outcome: ReceiptOutcome, now: datetime, config: PromotionAdaptorConfig
) -> dict[str, Any]:
    if outcome.kind == OutcomeKind.APPLIED:
        return {
            "state": OutboxState.APPLIED,
            "last_reason": "",
            "due_at": None,
            "applied_contact_log_id": outcome.contact_log_id,
        }
    if outcome.kind in _PAUSE:
        return {
            "state": OutboxState.PAUSED,
            "last_reason": outcome.reason,
            "due_at": None,
        }
    if outcome.kind in _RECONCILE:
        return {
            "state": OutboxState.RECONCILIATION_REQUIRED,
            "last_reason": outcome.reason,
            "due_at": None,
        }
    if lease.attempts >= config.max_attempts:
        return {
            "state": OutboxState.RECONCILIATION_REQUIRED,
            "last_reason": RETRIES_EXHAUSTED,
            "due_at": None,
        }
    delay = backoff_seconds(lease.attempts, outcome.retry_after, config)
    return {
        "state": OutboxState.RETRY,
        "last_reason": outcome.reason,
        "due_at": now + timedelta(seconds=delay),
    }


def finalize(
    lease: Lease,
    outcome: ReceiptOutcome,
    *,
    now: datetime,
    config: PromotionAdaptorConfig,
) -> bool:
    """Record ``outcome`` if ``lease`` is still the row's active lease."""
    return _finalize(lease, outcome, now, config) is not None


def _finalize(
    lease: Lease, outcome: ReceiptOutcome, now: datetime, config: PromotionAdaptorConfig
) -> dict[str, Any] | None:
    fields = _next_state(lease, outcome, now, config)
    with transaction.atomic(durable=True):
        changed = PromotionContactOutbox.objects.filter(
            pk=lease.pk, state=OutboxState.IN_FLIGHT, lease_token=lease.token
        ).update(**fields, lease_token=None, lease_expires_at=None, updated_at=now)
    if not changed:
        log.warning(
            "promo_dispatch_late_outcome_discarded",
            system="org",
            subsystem="integration",
            org_id=lease.org_id,
            send_id=lease.local_send_id,
            delivery_id=lease.delivery_id,
            outcome=outcome.kind.value,
        )
        return None
    log.info(
        "promo_dispatch_attempt_finished",
        system="org",
        subsystem="integration",
        org_id=lease.org_id,
        send_id=lease.local_send_id,
        delivery_id=lease.delivery_id,
        attempts=lease.attempts,
        http_status=outcome.http_status,
        outcome=outcome.kind.value,
        state=fields["state"],
        reason=fields["last_reason"] or None,
    )
    return fields


def _log_finished(
    row: PromotionContactOutbox, attempts: int, state: str, reason: str
) -> None:
    log.info(
        "promo_dispatch_attempt_finished",
        system="org",
        subsystem="integration",
        org_id=row.organization_id,
        send_id=row.local_send_id,
        delivery_id=str(row.delivery_id),
        attempts=attempts,
        http_status=None,
        outcome=None,
        state=state,
        reason=reason,
    )


def preview_due(
    *, limit: int = 100, now: datetime | None = None, resume_paused: bool = False
) -> DispatchReport:
    """What ``dispatch_due`` would attempt, without leasing or sending."""
    now = now or timezone.now()
    due = _due(now)
    if resume_paused:
        due |= Q(state=OutboxState.PAUSED)
    rows = PromotionContactOutbox.objects.filter(due)
    bound = _bound()
    report = DispatchReport(enabled=_config().enabled, dry_run=True)
    report.due = min(limit, rows.filter(bound).count())
    report.skipped_unbound = rows.exclude(bound).count()
    if resume_paused:
        report.resumed = rows.filter(bound, state=OutboxState.PAUSED).count()
    return report


def dispatch_due(
    *,
    limit: int = 100,
    now: datetime | None = None,
    resume_paused: bool = False,
    client: ReceiptClient | None = None,
) -> DispatchReport:
    config = _config()
    if not config.enabled:
        log.info("promo_dispatch_disabled", system="org", subsystem="integration")
        return DispatchReport(enabled=False)
    now = now or timezone.now()
    if client is None:
        client = PromotionAdaptorClient(config)
    report = DispatchReport(enabled=True)
    bound = _bound()
    if resume_paused:
        with transaction.atomic(durable=True):
            report.resumed = PromotionContactOutbox.objects.filter(
                bound, state=OutboxState.PAUSED
            ).update(
                state=OutboxState.PENDING, due_at=now, last_reason="", updated_at=now
            )
        if report.resumed:
            log.info(
                "promo_dispatch_resumed",
                system="org",
                subsystem="integration",
                resumed=report.resumed,
            )
    due = PromotionContactOutbox.objects.filter(_due(now))
    report.skipped_unbound = due.exclude(bound).count()
    rows = list(due.filter(bound).order_by("due_at", "pk")[:limit])
    report.due = len(rows)
    for row in rows:
        lease = claim(row, now=now, config=config)
        if lease is None:
            continue
        report.leased += 1
        try:
            outcome = client.record(lease.payload)
        except Exception:  # noqa: BLE001 - an unexpected client bug is retried
            log.exception(
                "promo_dispatch_client_failed",
                system="org",
                subsystem="integration",
                org_id=lease.org_id,
                send_id=lease.local_send_id,
                delivery_id=lease.delivery_id,
            )
            outcome = ReceiptOutcome(OutcomeKind.RETRYABLE, DISPATCH_ERROR, None)
        fields = _finalize(lease, outcome, now, config)
        if fields is None:
            report.discarded += 1
            continue
        report.counts[str(fields["state"])] += 1
        if fields["last_reason"]:
            report.reasons[fields["last_reason"]] += 1
    log.info(
        "promo_dispatch_run_finished",
        system="org",
        subsystem="integration",
        due=report.due,
        leased=report.leased,
        resumed=report.resumed,
        discarded=report.discarded,
        skipped_unbound=report.skipped_unbound,
        counts=dict(report.counts),
    )
    return report
