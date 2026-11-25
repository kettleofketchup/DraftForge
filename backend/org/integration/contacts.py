"""Import the bound guild's external contact log and answer "was this
person contacted?".

``import_contact_receipts`` takes one id range of the external contact log
(``parse_import_batch``): every source row with ``after < id <= through``
is an entry or a skipped id. The whole batch is validated before anything
is written; it then runs under the org row lock and the lock of every event
it touches, taken in ascending order (``event_lock.with_event_mutations``),
the same per-event lock a local record-send takes. Per entry it returns:

- ``applied``: a new source contact, stored once whoever the player is (an
  unknown player is stored with no account);
- ``unchanged``: stored with the same source facts, target, promoter and
  bound event. A verified association change (null to the account that
  owns the Discord ID, null to that account's membership here) is saved and
  counted in ``association_updated``; the source facts and import time stay;
- ``updated``: any of those differ, so the receipt is superseded
  (``points.supersede``) and audited;
- ``reinstated``: a retracted receipt was posted again;
- ``quarantined``: the stored association conflicts with the incoming one
  (the Discord ID now belongs to another account, or the membership is
  someone else's). Only that entry is quarantined.

Each entry also reports its ``point`` (``points.settle``) and whether it
voided a local point. Stored, live receipts inside the range that were
neither posted nor skipped are retracted, unless they were imported after
this scan started (less a grace period), so an older scan never retracts a
newer scan's row. Nothing here creates an account, a membership or a
``PromoSend``.

The event comes only from DraftForge's own binding (occasion -> event of
this org); date-linked contacts and unbound occasions have none.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final, Literal

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Max
from django.utils import timezone

from app.models import CustomUser
from config.promotion_sync import OrgPromotionBinding
from events.models import Event
from org.integration import points
from org.integration.bindings import get_org_binding
from org.integration.errors import IntegrationError, invalid
from org.integration.event_lock import with_event_mutations
from org.integration.parsers import (
    MAX_BATCH,
    expect_object,
    parse_batch,
    parse_choice,
    parse_date,
    parse_id,
    parse_timestamp,
)
from org.integration.receipts import format_timestamp, import_source_hash
from org.integration.ticks import (
    external_contact_exists,
    external_contact_for,
    external_contacts,
    suppressing_receipts,
)
from org.models import Organization, OrgUser
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ContactMethod,
    ContactReason,
    ExternalPromotionReceipt,
    PointStatus,
    ReceiptSource,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

__all__ = [
    "AssociationOutcome",
    "ContactReason",
    "ImportBatch",
    "ImportEntry",
    "contact_sync_status",
    "external_contact_exists",
    "external_contact_for",
    "external_contacts",
    "import_contact_receipts",
    "parse_import_batch",
    "reconcile_association",
    "suppressing_receipts",
]

Status = Literal["applied", "unchanged", "updated", "reinstated", "quarantined"]


@dataclass(frozen=True)
class AssociationOutcome:
    status: Literal["unchanged", "quarantined"]
    association_updated: bool


BATCH_KEYS: Final[tuple[str, ...]] = (
    "source",
    "guild_id",
    "scan_started_at",
    "range",
    "skipped_ids",
    "entries",
)
RANGE_KEYS: Final[tuple[str, ...]] = ("after", "through")
IMPORT_ENTRY_KEYS: Final[tuple[str, ...]] = (
    "source_contact_id",
    "target_discord_id",
    "promoter_discord_id",
    "recorded_at",
    "contact_date_ny",
    "contact_method",
    "contact_reason",
    "occasion_id",
    "event_date",
    "forced",
)
MAX_SKIPPED: Final[int] = 1000


@dataclass(frozen=True)
class ImportEntry:
    """One parsed entry of the guild-wide import."""

    source_contact_id: int
    target_discord_id: str
    promoter_discord_id: str | None
    recorded_at: datetime
    contact_date_ny: date
    contact_method: str
    contact_reason: str
    occasion_id: int | None
    event_date: datetime | None
    forced: bool
    source_hash: str


@dataclass(frozen=True)
class ImportBatch:
    """A parsed guild-wide import batch.

    ``range_after``/``range_through`` are both ``None`` for the watermark
    probe (no entries, no skipped ids); otherwise every source row with
    ``range_after < id <= range_through`` is an entry or a skipped id.
    """

    guild_id: str
    scan_started_at: datetime
    range_after: int | None
    range_through: int | None
    skipped_ids: frozenset[int]
    entries: list[ImportEntry]


def _parse_import_entry(value: Any, path: str, now: datetime) -> ImportEntry:
    raw = expect_object(value, path, IMPORT_ENTRY_KEYS)
    source_contact_id = parse_id(raw["source_contact_id"], f"{path}.source_contact_id")
    target = parse_id(raw["target_discord_id"], f"{path}.target_discord_id")
    promoter = parse_id(
        raw["promoter_discord_id"], f"{path}.promoter_discord_id", nullable=True
    )
    assert source_contact_id is not None and target is not None
    recorded_at = parse_timestamp(raw["recorded_at"], f"{path}.recorded_at", now=now)
    contact_date_ny = parse_date(raw["contact_date_ny"], f"{path}.contact_date_ny")
    contact_method = parse_choice(
        raw["contact_method"], f"{path}.contact_method", ContactMethod.values
    )
    contact_reason = parse_choice(
        raw["contact_reason"], f"{path}.contact_reason", ContactReason.values
    )
    occasion_id = parse_id(raw["occasion_id"], f"{path}.occasion_id", nullable=True)
    event_date = (
        None
        if raw["event_date"] is None
        else parse_timestamp(raw["event_date"], f"{path}.event_date", bounded=False)
    )
    if (occasion_id is None) == (event_date is None):
        raise invalid(path, "must set exactly one of occasion_id and event_date")
    forced = raw["forced"]
    if not isinstance(forced, bool):
        raise invalid(f"{path}.forced", "must be a boolean")
    if forced and occasion_id is None:
        raise invalid(f"{path}.forced", "requires occasion_id")
    source_hash = import_source_hash(
        {
            "source_contact_id": str(source_contact_id),
            "recorded_at": recorded_at,
            "contact_date_ny": contact_date_ny.isoformat(),
            "contact_method": contact_method,
            "contact_reason": contact_reason,
            "occasion_id": None if occasion_id is None else str(occasion_id),
            "event_date": event_date,
            "forced": forced,
        },
        source=ReceiptSource.CONTACT_LOG,
    )
    return ImportEntry(
        source_contact_id=source_contact_id,
        target_discord_id=str(target),
        promoter_discord_id=None if promoter is None else str(promoter),
        recorded_at=recorded_at,
        contact_date_ny=contact_date_ny,
        contact_method=contact_method,
        contact_reason=contact_reason,
        occasion_id=occasion_id,
        event_date=event_date,
        forced=forced,
        source_hash=source_hash,
    )


def _parse_range(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    raw = expect_object(value, "range", RANGE_KEYS)
    after = 0 if raw["after"] == "0" else parse_id(raw["after"], "range.after")
    through = parse_id(raw["through"], "range.through")
    assert after is not None and through is not None
    if after >= through:
        raise invalid("range", "after must be below through")
    return after, through


def parse_import_batch(payload: Any, *, now: datetime | None = None) -> ImportBatch:
    """Parse one guild-wide import body, or raise a 400 ``IntegrationError``.

    Checks the exact key sets, the per-entry rules (canonical ids, a
    ``recorded_at`` at most five minutes ahead of ``now``, a real
    ``contact_date_ny``, known enums, exactly one of ``occasion_id`` and
    ``event_date``, ``forced`` only with an occasion) and the range rules:
    a null range carries nothing, and every entry and skipped id lies in
    ``after < id <= through``, unique across both lists. Binding checks on
    ``guild_id`` are the caller's.
    """
    now = now or timezone.now()
    body = expect_object(payload, "", BATCH_KEYS)
    parse_choice(body["source"], "source", (ReceiptSource.CONTACT_LOG,))
    guild_id = parse_id(body["guild_id"], "guild_id")
    scan_started_at = parse_timestamp(
        body["scan_started_at"], "scan_started_at", now=now
    )
    bounds = _parse_range(body["range"])
    raw_skipped = parse_batch(
        body["skipped_ids"], "skipped_ids", min_items=0, max_items=MAX_SKIPPED
    )
    raw_entries = parse_batch(
        body["entries"], "entries", min_items=0, max_items=MAX_BATCH
    )
    if bounds is None and (raw_skipped or raw_entries):
        raise invalid("range", "is required when the batch has entries or skipped ids")

    def check_in_range(source_id: int, path: str) -> None:
        assert bounds is not None
        if not bounds[0] < source_id <= bounds[1]:
            raise invalid(path, "lies outside range")

    skipped: set[int] = set()
    for i, value in enumerate(raw_skipped):
        path = f"skipped_ids[{i}]"
        source_id = parse_id(value, path)
        assert source_id is not None
        check_in_range(source_id, path)
        if source_id in skipped:
            raise invalid(path, "is repeated in the batch")
        skipped.add(source_id)
    entries: list[ImportEntry] = []
    seen: set[int] = set()
    for i, value in enumerate(raw_entries):
        path = f"entries[{i}]"
        entry = _parse_import_entry(value, path, now)
        check_in_range(entry.source_contact_id, f"{path}.source_contact_id")
        if entry.source_contact_id in seen or entry.source_contact_id in skipped:
            raise invalid(
                f"{path}.source_contact_id", "is repeated in the batch or skipped"
            )
        seen.add(entry.source_contact_id)
        entries.append(entry)
    return ImportBatch(
        guild_id=str(guild_id),
        scan_started_at=scan_started_at,
        range_after=None if bounds is None else bounds[0],
        range_through=None if bounds is None else bounds[1],
        skipped_ids=frozenset(skipped),
        entries=entries,
    )


RETRACT_GRACE: Final = timedelta(minutes=5)
HISTORY_WARNING: Final[str] = "history_may_be_incomplete"
_COUNTED_POINTS: Final[tuple[str, ...]] = (
    PointStatus.CREDITED,
    PointStatus.UNCREDITED,
    PointStatus.DUPLICATE,
    PointStatus.ECHO,
)


class _LockSetChanged(Exception):
    """A receipt moved to an event outside the locks taken for the batch."""


def _bound_events(org: Organization, binding: OrgPromotionBinding) -> dict[int, Event]:
    """Occasion id -> bound event, for events that exist in this org."""
    events = Event.objects.nocache().filter(
        pk__in=list(binding.events), organization=org
    )
    by_pk = {event.pk: event for event in events}
    return {
        occasion: by_pk[event_id]
        for event_id, occasion in binding.events.items()
        if event_id in by_pk
    }


def _event_for(entry: ImportEntry, events: dict[int, Event]) -> Event | None:
    return None if entry.occasion_id is None else events.get(entry.occasion_id)


def _read(
    org: Organization, batch: ImportBatch
) -> tuple[dict[int, ExternalPromotionReceipt], list[ExternalPromotionReceipt]]:
    """Retained receipts by source id, and the retraction candidates: live
    receipts inside the range that were neither posted nor skipped."""
    stored = ExternalPromotionReceipt.objects.filter(
        organization=org, source=ReceiptSource.CONTACT_LOG
    )
    entry_ids = {e.source_contact_id for e in batch.entries}
    retained = {
        r.source_contact_id: r for r in stored.filter(source_contact_id__in=entry_ids)
    }
    candidates: list[ExternalPromotionReceipt] = []
    if batch.range_through is not None:
        excluded = entry_ids | batch.skipped_ids
        candidates = [
            r
            for r in stored.filter(
                source_contact_id__gt=batch.range_after,
                source_contact_id__lte=batch.range_through,
                retracted_at__isnull=True,
            ).order_by("source_contact_id")
            if r.source_contact_id not in excluded
        ]
    return retained, candidates


def _lock_set(
    batch: ImportBatch,
    events: dict[int, Event],
    receipts: list[ExternalPromotionReceipt],
) -> set[int]:
    wanted = {
        event.pk
        for event in (_event_for(e, events) for e in batch.entries)
        if event is not None
    }
    return wanted | {r.event_id for r in receipts if r.event_id is not None}


def _resolve(
    org: Organization, discord_id: str
) -> tuple[CustomUser | None, OrgUser | None]:
    user = CustomUser.objects.nocache().filter(discordId=discord_id).first()
    if user is None:
        return None, None
    org_user = OrgUser.objects.nocache().filter(user=user, organization=org).first()
    return user, org_user


def _create(
    org: Organization,
    entry: ImportEntry,
    event: Event | None,
    user: CustomUser | None,
    org_user: OrgUser | None,
) -> ExternalPromotionReceipt:
    now = timezone.now()
    return ExternalPromotionReceipt.objects.create(
        organization=org,
        source=ReceiptSource.CONTACT_LOG,
        source_contact_id=entry.source_contact_id,
        first_imported_at=now,
        recorded_at=entry.recorded_at,
        contact_date_ny=entry.contact_date_ny,
        contact_method=entry.contact_method,
        contact_reason=entry.contact_reason,
        occasion_id=entry.occasion_id,
        event_date=entry.event_date,
        forced=entry.forced,
        source_hash=entry.source_hash,
        discord_id=entry.target_discord_id,
        promoter_discord_id=entry.promoter_discord_id or "",
        event=event,
        user=user,
        org_user=org_user,
        association_state=(
            AssociationState.LINKED if user is not None else AssociationState.UNRESOLVED
        ),
        association_updated_at=now,
    )


def _relink(
    receipt: ExternalPromotionReceipt,
    user: CustomUser | None,
    org_user: OrgUser | None,
) -> None:
    """A new target Discord ID is a new identity: resolve it afresh."""
    receipt.user = user
    receipt.org_user = org_user
    receipt.association_state = (
        AssociationState.LINKED if user is not None else AssociationState.UNRESOLVED
    )
    receipt.association_reason = AssociationReason.NONE
    receipt.association_updated_at = timezone.now()
    receipt.save(
        update_fields=[
            "user",
            "org_user",
            "association_state",
            "association_reason",
            "association_updated_at",
        ]
    )


def _differs(
    receipt: ExternalPromotionReceipt, entry: ImportEntry, event: Event | None
) -> bool:
    return (
        receipt.source_hash != entry.source_hash
        or receipt.discord_id != entry.target_discord_id
        or receipt.promoter_discord_id != (entry.promoter_discord_id or "")
        or receipt.event_id != (event.pk if event is not None else None)
    )


@dataclass(frozen=True)
class _Replay:
    status: Status
    outcome: points.PointOutcome
    association_updated: bool
    changed: bool


def _replay(
    receipt: ExternalPromotionReceipt,
    entry: ImportEntry,
    event: Event | None,
    user: CustomUser | None,
    org_user: OrgUser | None,
) -> _Replay:
    """Apply a posted entry to its stored receipt (replay rules, spec order:
    retraction, source hash, target, promoter, bound event)."""
    receipt.refresh_from_db()
    association_updated = False
    quarantined = False
    if receipt.discord_id == entry.target_discord_id:
        association = reconcile_association(
            receipt,
            user.pk if user is not None else None,
            org_user.pk if org_user is not None else None,
        )
        quarantined = association.status == "quarantined"
        association_updated = association.association_updated
    else:
        _relink(receipt, user, org_user)
    reinstated = receipt.retracted_at is not None
    if reinstated:
        receipt.retracted_at = None
        receipt.point_status = PointStatus.NOT_APPLICABLE
        receipt.save(update_fields=["retracted_at", "point_status"])
    changed = _differs(receipt, entry, event)
    if changed:
        outcome = points.supersede(receipt, entry, event)
    else:
        # The promoter may have become matchable since the last import.
        outcome = points.settle(receipt)
    status: Status
    if reinstated:
        status = "reinstated"
    elif changed:
        status = "updated"
    elif quarantined:
        status = "quarantined"
    else:
        status = "unchanged"
    return _Replay(status, outcome, association_updated, changed)


def _apply_batch(
    org: Organization,
    batch: ImportBatch,
    events: dict[int, Event],
    retained: dict[int, ExternalPromotionReceipt],
    candidates: list[ExternalPromotionReceipt],
) -> dict[str, Any]:
    """Write the validated batch. Runs inside the org and event locks."""
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, entry in enumerate(batch.entries):
        event = _event_for(entry, events)
        user, org_user = _resolve(org, entry.target_discord_id)
        receipt = retained.get(entry.source_contact_id)
        if receipt is None:
            receipt = _create(org, entry, event, user, org_user)
            status: Status = "applied"
            outcome = points.settle(receipt)
        else:
            replay = _replay(receipt, entry, event, user, org_user)
            status, outcome = replay.status, replay.outcome
            counts["association_updated"] += replay.association_updated
            if status == "reinstated" and replay.changed:
                counts["updated"] += 1
        counts[status] += 1
        if outcome.point in _COUNTED_POINTS:
            counts[outcome.point] += 1
        counts["voided_local"] += outcome.voided_local
        counts["restored_local"] += outcome.restored_local
        results.append(
            {
                "index": index,
                "status": status,
                "point": outcome.point,
                "voided_local": outcome.voided_local,
            }
        )
    threshold = batch.scan_started_at - RETRACT_GRACE
    for receipt in candidates:
        receipt.refresh_from_db()
        if receipt.retracted_at is not None or receipt.first_imported_at >= threshold:
            continue
        counts["restored_local"] += points.retract(receipt)
        counts["retracted"] += 1
    highest = ExternalPromotionReceipt.objects.filter(
        organization=org, source=ReceiptSource.CONTACT_LOG
    ).aggregate(highest=Max("source_contact_id"))["highest"]
    return {
        "results": results,
        **{
            key: counts[key]
            for key in (
                "applied",
                "unchanged",
                "updated",
                "reinstated",
                "quarantined",
                "association_updated",
                "retracted",
                "credited",
                "uncredited",
                "duplicate",
                "echo",
                "voided_local",
                "restored_local",
            )
        },
        "max_source_contact_id": None if highest is None else str(highest),
    }


def import_contact_receipts(org: Organization, payload: Any) -> dict[str, Any]:
    """Validate and apply one guild-wide batch atomically; see the module
    docstring.

    Raises ``IntegrationError``: 400 for an invalid batch, 403
    ``binding_missing`` / ``binding_mismatch`` for the binding and its guild,
    and 409 ``import_conflict_retry`` when a concurrent import stored one of
    the source ids first or moved a receipt to an event outside this
    batch's locks (retry once). Nothing is written when it raises.
    """
    batch = parse_import_batch(payload)
    binding = get_org_binding(org.pk)
    if batch.guild_id != str(binding.guild_id):
        raise IntegrationError("binding_mismatch", 403)
    events = _bound_events(org, binding)
    retained, candidates = _read(org, batch)
    lock_ids = _lock_set(batch, events, [*retained.values(), *candidates])

    def lock_org() -> None:
        # Serializes with rescoring, which locks the same row first. NO KEY
        # UPDATE, so a send holding an event lock can still insert rows that
        # reference the org (their foreign-key check takes KEY SHARE);
        # FOR UPDATE would deadlock against it.
        list(
            Organization.objects.nocache()
            .select_for_update(no_key=True)
            .filter(pk=org.pk)
            .values_list("pk", flat=True)
        )

    def locked() -> dict[str, Any]:
        retained, candidates = _read(org, batch)
        if not _lock_set(batch, events, [*retained.values(), *candidates]) <= lock_ids:
            raise _LockSetChanged
        return _apply_batch(org, batch, events, retained, candidates)

    try:
        result = with_event_mutations(sorted(lock_ids), locked, lock_first=lock_org)
    except (IntegrityError, _LockSetChanged, Event.DoesNotExist):
        log.warning(
            "integration_contacts_import_conflict",
            system="org",
            subsystem="integration",
            org_id=org.pk,
            entries=len(batch.entries),
        )
        raise IntegrationError("import_conflict_retry", 409) from None
    log.info(
        "integration_contacts_imported",
        system="org",
        subsystem="integration",
        org_id=org.pk,
        entries=len(batch.entries),
        skipped=len(batch.skipped_ids),
        events=len(lock_ids),
        **{k: v for k, v in result.items() if k not in ("results",)},
    )
    return result


def _quarantine(
    receipt: ExternalPromotionReceipt, reason: AssociationReason
) -> AssociationOutcome:
    receipt.association_state = AssociationState.QUARANTINED
    receipt.association_reason = reason
    receipt.association_updated_at = timezone.now()
    receipt.save(
        update_fields=[
            "association_state",
            "association_reason",
            "association_updated_at",
        ]
    )
    log.warning(
        "promo_receipt_quarantined",
        system="org",
        subsystem="integration",
        org_id=receipt.organization_id,
        event_id=receipt.event_id,
        receipt_id=receipt.pk,
        reason=str(reason),
    )
    return AssociationOutcome("quarantined", association_updated=False)


def reconcile_association(
    receipt: ExternalPromotionReceipt, user_id: int | None, org_user_id: int | None
) -> AssociationOutcome:
    """Compare an incoming association with the stored one, per the replay rule.

    Equal: ``unchanged``. Verified enrichment (stored null user to the
    account that owns the receipt's Discord ID; null membership to that
    account's membership in the receipt's org): saved, ``unchanged`` with
    ``association_updated``. A merge survivor needs no case here:
    ``lifecycle.reconcile_promotion_identity`` already moved the receipt to
    it, so the replay is equal. Anything else quarantines the receipt; a
    quarantined receipt stays quarantined. Source facts are never touched.
    """
    if receipt.association_state == AssociationState.QUARANTINED:
        return AssociationOutcome("quarantined", association_updated=False)
    if (receipt.user_id, receipt.org_user_id) == (user_id, org_user_id):
        return AssociationOutcome("unchanged", association_updated=False)

    if receipt.user_id != user_id:
        owns_discord = (
            user_id is not None
            and receipt.user_id is None
            and CustomUser.objects.nocache()
            .filter(pk=user_id, discordId=receipt.discord_id)
            .exists()
        )
        if not owns_discord:
            return _quarantine(receipt, AssociationReason.DISCORD_OWNER_CHANGED)

    if org_user_id is not None and org_user_id != receipt.org_user_id:
        own_membership = (
            OrgUser.objects.nocache()
            .filter(
                pk=org_user_id,
                user_id=user_id,
                organization_id=receipt.organization_id,
            )
            .exists()
        )
        if user_id is None or not own_membership:
            return _quarantine(receipt, AssociationReason.ORG_USER_MISMATCH)

    receipt.user_id = user_id
    receipt.org_user_id = org_user_id
    receipt.association_state = (
        AssociationState.LINKED if user_id is not None else AssociationState.UNRESOLVED
    )
    receipt.association_reason = AssociationReason.NONE
    receipt.association_updated_at = timezone.now()
    receipt.save(
        update_fields=[
            "user",
            "org_user",
            "association_state",
            "association_reason",
            "association_updated_at",
        ]
    )
    return AssociationOutcome("unchanged", association_updated=True)


def contact_sync_status(org: Organization, event: Event) -> dict[str, Any]:
    """Candidate-envelope ``contact_sync``. The import time is when the last
    receipt for this event arrived, not proof the history is complete."""
    binding = settings.PROMOTION_SYNC.for_org(org.pk)
    configured = binding is not None and event.pk in binding.events
    last = None
    if configured:
        last = ExternalPromotionReceipt.objects.filter(
            organization=org, event=event
        ).aggregate(last=Max("first_imported_at"))["last"]
    return {
        "configured": configured,
        "last_receipt_imported_at": format_timestamp(last) if last else None,
        "warning": HISTORY_WARNING if configured else None,
    }
