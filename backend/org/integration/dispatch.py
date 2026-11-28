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
is resent with the same delivery UUID and bytes.

``claim`` resolves the org's promotion stream inside its transaction, under
the org row lock that adoption also takes. An unadopted org's row goes over
the deployment transport only while its org and event are bound in
``PROMOTION_SYNC``. An adopted org's rows, null-connection rows included, go
only to the stream connection while it and its promotion push are enabled,
and are recorded with that connection when leased; otherwise they stay
pending (``held``). A row sent before its event binding became effective
moves to ``backlog_held`` until an org admin releases it. A connection row
also stays pending (``busy``) while the org already has its cap of outbound
requests in flight, counted under the same org lock the MMR paths take.

An ``applied`` answer is recorded under the org and event locks together with
reclassifying an already imported external copy of the send as its echo, so
both arrival orders settle the point once.

The clock is read again for each claim and after each answer, never once per
run: a run that sends many rows to a slow adaptor would otherwise lease later
rows already expired and schedule retries in the past.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Protocol

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from config.promotion_sync import PromotionAdaptorConfig
from events.models import Event
from org.api_connections.crypto import CredentialError, canonical_origin
from org.api_connections.limits import OUTBOUND_REQUESTS_PER_ORG
from org.api_connections.promotion_config import (
    adopted_org_ids,
    env_dispatch_bindings,
    resolve_promotion_config,
)
from org.api_connections.runs import outbound_busy
from org.integration import points
from org.integration.adaptor_client import (
    ConnectionReceiptClient,
    OutcomeKind,
    PromotionAdaptorClient,
    ReceiptOutcome,
)
from org.integration.event_lock import with_event_mutations
from org.integration.receipts import canonical_receipt_hash
from org.models import Organization, OrgApiConnection
from org.models_promotion_sync import (
    ExternalPromotionReceipt,
    OutboxState,
    PromotionContactOutbox,
    ReceiptSource,
)
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


ACK_LOCK_ATTEMPTS: Final[int] = 3


class ReceiptClient(Protocol):
    def record(self, payload: dict[str, Any]) -> ReceiptOutcome: ...


class ConnectionClient(Protocol):
    def record(
        self,
        payload: dict[str, Any],
        *,
        connection_id: int,
        origin: str,
        config_version: int,
    ) -> ReceiptOutcome: ...


@dataclass(frozen=True)
class Lease:
    pk: int
    token: uuid.UUID
    attempts: int
    org_id: int
    local_send_id: int
    delivery_id: str
    payload: dict[str, Any]
    connection_id: int | None = None
    origin: str = ""
    config_version: int = 0


@dataclass(frozen=True)
class _Route:
    kind: str
    connection_id: int | None = None
    origin: str = ""
    config_version: int = 0


class _LockSetChanged(Exception):
    pass


@dataclass
class DispatchReport:
    enabled: bool
    dry_run: bool = False
    due: int = 0
    resumed: int = 0
    leased: int = 0
    discarded: int = 0
    skipped_unbound: int = 0
    held: int = 0
    busy: int = 0
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
            "held": self.held,
            "busy": self.busy,
            "counts": dict(sorted(self.counts.items())),
            "reasons": dict(sorted(self.reasons.items())),
        }


def _config() -> PromotionAdaptorConfig:
    return settings.PROMOTION_ADAPTOR


def _bound() -> Q:
    """Rows of unadopted orgs whose org and event are both deployment-bound."""
    q = Q(pk__in=[])
    for binding in env_dispatch_bindings():
        if binding.events:
            q |= Q(organization_id=binding.org_id, event_id__in=list(binding.events))
    return q


def _candidates(config: PromotionAdaptorConfig) -> Q:
    """Rows a run looks at; ``claim`` decides each one again under lock."""
    q = _bound() if config.enabled else Q(pk__in=[])
    adopted = adopted_org_ids()
    if adopted:
        q |= Q(organization_id__in=adopted)
    return q


def _lock_org(org_id: int) -> None:
    # NO KEY UPDATE: serializes with adoption (FOR UPDATE) and imports,
    # while sends may still insert rows referencing the org.
    list(
        Organization.objects.nocache()
        .select_for_update(no_key=True)
        .filter(pk=org_id)
        .values_list("pk", flat=True)
    )


def _route(row: PromotionContactOutbox) -> _Route:
    resolved = resolve_promotion_config(row.organization_id)
    if row.event_id not in resolved.events:
        return _Route("held")
    if not resolved.adopted:
        return _Route("env" if resolved.transport == "env" else "held")
    if resolved.transport != "connection" or resolved.connection_id is None:
        return _Route("held")
    if row.connection_id != resolved.connection_id:
        effective = resolved.effective_at.get(row.event_id)
        if effective is not None and row.sent_at < effective:
            return _Route("backlog")
    connection = OrgApiConnection.objects.get(pk=resolved.connection_id)
    try:
        origin = canonical_origin(connection.outbound_base_url)
    except CredentialError:
        return _Route("held")
    return _Route(
        "connection",
        connection_id=connection.pk,
        origin=origin,
        config_version=connection.config_version,
    )


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
    return _claim(row, now=now, config=config)[0]


def _claim(
    row: PromotionContactOutbox, *, now: datetime, config: PromotionAdaptorConfig
) -> tuple[Lease | None, str]:
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
            return None, "changed"
        _lock_org(row.organization_id)
        route = _route(row)
        if route.kind == "held":
            return None, "held"
        if route.kind == "backlog":
            moved = current.update(
                state=OutboxState.BACKLOG_HELD,
                last_reason="",
                due_at=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
            if moved:
                _log_finished(row, row.attempts, OutboxState.BACKLOG_HELD, "")
            return None, OutboxState.BACKLOG_HELD if moved else "changed"
        if (
            route.connection_id is not None
            and outbound_busy(row.organization_id, now) >= OUTBOUND_REQUESTS_PER_ORG
        ):
            return None, "busy"
        token = uuid.uuid4()
        extra: dict[str, Any] = {}
        if route.connection_id is not None:
            extra["connection_id"] = route.connection_id
        moved = current.update(
            state=OutboxState.IN_FLIGHT,
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=lease_seconds(config)),
            attempts=F("attempts") + 1,
            updated_at=now,
            **extra,
        )
    if not moved:
        return None, "changed"
    assert row.payload is not None
    return (
        Lease(
            pk=row.pk,
            token=token,
            attempts=row.attempts + 1,
            org_id=row.organization_id,
            local_send_id=row.local_send_id,
            delivery_id=str(row.delivery_id),
            payload=row.payload,
            connection_id=route.connection_id,
            origin=route.origin,
            config_version=route.config_version,
        ),
        "leased",
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
    if fields["state"] == OutboxState.APPLIED:
        changed = _record_applied(lease, fields, now)
    else:
        with transaction.atomic(durable=True):
            changed = _mark(lease, fields, now)
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


def _mark(lease: Lease, fields: dict[str, Any], now: datetime) -> int:
    return PromotionContactOutbox.objects.filter(
        pk=lease.pk, state=OutboxState.IN_FLIGHT, lease_token=lease.token
    ).update(**fields, lease_token=None, lease_expires_at=None, updated_at=now)


def _record_applied(lease: Lease, fields: dict[str, Any], now: datetime) -> int:
    """Mark the row applied and reclassify its imported echo in one transaction."""
    receipts = ExternalPromotionReceipt.objects.filter(
        organization_id=lease.org_id,
        source=ReceiptSource.CONTACT_LOG,
        source_contact_id=fields["applied_contact_log_id"],
    )
    for _ in range(ACK_LOCK_ATTEMPTS):
        events = {e for e in receipts.values_list("event_id", flat=True) if e}

        def locked() -> int:
            held = {e for e in receipts.values_list("event_id", flat=True) if e}
            if not held <= events:
                raise _LockSetChanged
            changed = _mark(lease, fields, now)
            if changed:
                for receipt in receipts.order_by("pk"):
                    points.reclassify_echo(receipt)
            return changed

        try:
            return with_event_mutations(
                sorted(events), locked, lock_first=lambda: _lock_org(lease.org_id)
            )
        except (_LockSetChanged, Event.DoesNotExist):
            continue
    log.warning(
        "promo_dispatch_ack_lock_contended",
        system="org",
        subsystem="integration",
        org_id=lease.org_id,
        delivery_id=lease.delivery_id,
    )
    return 0


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
    bound = _candidates(_config())
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
    connection_client: ConnectionClient | None = None,
    clock: Callable[[], datetime] = timezone.now,
    organization_ids: Collection[int] | None = None,
) -> DispatchReport:
    """Lease, send and finalize up to ``limit`` due rows.

    ``clock`` is read before each claim and after each answer. ``now``
    pins it to one instant, for tests only. ``organization_ids`` limits the
    run to those orgs' rows.
    """
    config = _config()
    if not config.enabled and not adopted_org_ids():
        log.info("promo_dispatch_disabled", system="org", subsystem="integration")
        return DispatchReport(enabled=False)
    if now is not None:
        pinned = now
        clock = lambda: pinned  # noqa: E731
    now = clock()
    if client is None and config.enabled:
        client = PromotionAdaptorClient(config)
    if connection_client is None:
        connection_client = ConnectionReceiptClient()
    report = DispatchReport(enabled=True)
    bound = _candidates(config)
    if organization_ids is not None:
        bound &= Q(organization_id__in=list(organization_ids))
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
        lease, status = _claim(row, now=clock(), config=config)
        if lease is None:
            if status == "held":
                report.held += 1
            elif status == "busy":
                report.busy += 1
            elif status == OutboxState.BACKLOG_HELD:
                report.counts[status] += 1
            continue
        report.leased += 1
        try:
            if lease.connection_id is not None:
                outcome = connection_client.record(
                    lease.payload,
                    connection_id=lease.connection_id,
                    origin=lease.origin,
                    config_version=lease.config_version,
                )
            else:
                assert client is not None
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
        fields = _finalize(lease, outcome, clock(), config)
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
        held=report.held,
        busy=report.busy,
        counts=dict(report.counts),
    )
    return report
