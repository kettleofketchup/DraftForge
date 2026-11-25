"""Import external contact receipts and answer "was this person contacted?".

``import_contact_receipts`` is all or nothing. It validates the whole batch
(shape, one bound event, occasion linkage, the current ``mapping_version``,
every subject tuple against the authorized universe, and every retained
source ID's immutable facts) before writing anything, then writes inside
the event's mutation lock (``event_lock.with_event_mutation``), the same
lock a local record-send takes. Per entry it returns:

- ``applied``: a new source contact, stored once;
- ``unchanged``: the source contact is already stored with the same facts.
  A verified association change (null to the account that owns the Discord
  ID, null to that account's membership here) is saved and counted in
  ``association_updated``; the source facts and import time stay as they
  were;
- ``quarantined``: the stored association conflicts with the incoming one
  (the Discord ID now belongs to another account, or the membership is
  someone else's). Only that entry is quarantined: its evidence is kept
  and it stops ticking. The rest of the batch still applies.

A retained source ID with different source facts is 409
``source_content_conflict`` for the whole batch. Nothing here creates an
account, a membership, a ``PromoSend`` or an award.

Ticks: a non-quarantined receipt for the event and Discord ID suppresses
the candidate row with that Discord ID, provided the receipt is not linked
to a different account than the row's.

``parse_import_batch`` parses the guild-wide import wire that replaces the
per-event one above: every external contact of the bound guild in one id
range, each entry linked to an occasion or an event date, with the rows
the adaptor read but did not post listed in ``skipped_ids``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final, Literal

from django.conf import settings
from django.db import IntegrityError, models
from django.db.models import Max
from django.utils import timezone

from app.models import CustomUser
from events.models import Event
from org.integration.bindings import get_event_binding, get_org_binding
from org.integration.errors import IntegrationError, invalid
from org.integration.event_lock import with_event_mutation
from org.integration.parsers import (
    MAX_BATCH,
    expect_object,
    parse_batch,
    parse_choice,
    parse_date,
    parse_hash,
    parse_id,
    parse_timestamp,
)
from org.integration.receipts import (
    _legacy_import_source_hash,
    format_timestamp,
    import_source_hash,
)
from org.integration.subjects import (
    SubjectUniverse,
    authorized_event_subjects,
    guild_snapshot,
)
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
    ContactLinkage,
    ContactMethod,
    ExternalPromotionReceipt,
    ReceiptSource,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

__all__ = [
    "AssociationOutcome",
    "ContactReason",
    "ImportBatch",
    "ImportEntryV",
    "contact_sync_status",
    "external_contact_exists",
    "external_contact_for",
    "external_contacts",
    "import_contact_receipts",
    "parse_import_batch",
    "reconcile_association",
    "suppressing_receipts",
]

ENVELOPE_KEYS: Final[tuple[str, ...]] = ("source", "mapping_version", "entries")
ENTRY_KEYS: Final[tuple[str, ...]] = (
    "source_contact_id",
    "event_id",
    "user_id",
    "org_user_id",
    "discord_id",
    "recorded_at",
    "contact_method",
    "linkage",
)
# v1 supports occasion linkage only; no event-date fallback is configured.
SUPPORTED_LINKAGE: Final[str] = ContactLinkage.OCCASION
HISTORY_WARNING: Final[str] = "history_may_be_incomplete"

Status = Literal["applied", "unchanged", "quarantined"]


@dataclass(frozen=True)
class ImportEntry:
    index: int
    source_contact_id: int
    event_id: int
    user_id: int | None
    org_user_id: int | None
    discord_id: str
    recorded_at: datetime
    contact_method: str
    linkage: str

    @property
    def source_hash(self) -> str:
        return _legacy_import_source_hash(
            {
                "source_contact_id": str(self.source_contact_id),
                "event_id": str(self.event_id),
                "discord_id": self.discord_id,
                "recorded_at": self.recorded_at,
                "contact_method": self.contact_method,
                "linkage": self.linkage,
            },
            source=ReceiptSource.CONTACT_LOG,
        )


@dataclass(frozen=True)
class AssociationOutcome:
    status: Literal["unchanged", "quarantined"]
    association_updated: bool


def _parse_entry(value: Any, index: int) -> ImportEntry:
    path = f"entries[{index}]"
    raw = expect_object(value, path, ENTRY_KEYS)
    source_contact_id = parse_id(raw["source_contact_id"], f"{path}.source_contact_id")
    event_id = parse_id(raw["event_id"], f"{path}.event_id")
    discord_id = parse_id(raw["discord_id"], f"{path}.discord_id")
    assert source_contact_id is not None and event_id is not None
    linkage = parse_choice(raw["linkage"], f"{path}.linkage", ContactLinkage.values)
    if linkage != SUPPORTED_LINKAGE:
        raise invalid(f"{path}.linkage", "is not the event's configured linkage")
    return ImportEntry(
        index=index,
        source_contact_id=source_contact_id,
        event_id=event_id,
        user_id=parse_id(raw["user_id"], f"{path}.user_id", nullable=True),
        org_user_id=parse_id(raw["org_user_id"], f"{path}.org_user_id", nullable=True),
        discord_id=str(discord_id),
        recorded_at=parse_timestamp(raw["recorded_at"], f"{path}.recorded_at"),
        contact_method=parse_choice(
            raw["contact_method"], f"{path}.contact_method", ContactMethod.values
        ),
        linkage=linkage,
    )


def _parse(payload: Any) -> tuple[str, list[ImportEntry]]:
    body = expect_object(payload, "", ENVELOPE_KEYS)
    parse_choice(body["source"], "source", (ReceiptSource.CONTACT_LOG,))
    version = parse_hash(body["mapping_version"], "mapping_version")
    raw_entries = parse_batch(body["entries"], "entries", min_items=0)
    entries = [_parse_entry(value, i) for i, value in enumerate(raw_entries)]
    seen: set[int] = set()
    for entry in entries:
        if entry.source_contact_id in seen:
            raise invalid(
                f"entries[{entry.index}].source_contact_id", "is repeated in the batch"
            )
        seen.add(entry.source_contact_id)
    if len({e.event_id for e in entries}) > 1:
        raise invalid("entries", "must all be for one event")
    return version, entries


class ContactReason(models.TextChoices):
    EVENT_INVITE = "EVENT_INVITE", "Event invite"
    FOLLOW_UP = "FOLLOW_UP", "Follow-up"
    GENERAL = "GENERAL", "General"


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
class ImportEntryV:
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
    entries: list[ImportEntryV]


def _parse_import_entry(value: Any, path: str, now: datetime) -> ImportEntryV:
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
    return ImportEntryV(
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
    entries: list[ImportEntryV] = []
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


def _result(statuses: list[Status], association_updated: int) -> dict[str, Any]:
    return {
        "results": [{"index": i, "status": s} for i, s in enumerate(statuses)],
        "applied": statuses.count("applied"),
        "unchanged": statuses.count("unchanged"),
        "quarantined": statuses.count("quarantined"),
        "association_updated": association_updated,
    }


def _authorize(universe: SubjectUniverse, entries: list[ImportEntry]) -> None:
    for entry in entries:
        subject = universe.by_discord_id(entry.discord_id)
        if subject is None or (subject.user_id, subject.org_user_id) != (
            entry.user_id,
            entry.org_user_id,
        ):
            raise invalid(
                f"entries[{entry.index}]", "is not an authorized subject for the event"
            )


def _retained(
    org: Organization, entries: list[ImportEntry]
) -> dict[int, ExternalPromotionReceipt]:
    stored = ExternalPromotionReceipt.objects.filter(
        organization=org,
        source=ReceiptSource.CONTACT_LOG,
        source_contact_id__in=[e.source_contact_id for e in entries],
    )
    by_id = {r.source_contact_id: r for r in stored}
    for entry in entries:
        receipt = by_id.get(entry.source_contact_id)
        if receipt is not None and receipt.source_hash != entry.source_hash:
            raise IntegrationError("source_content_conflict", 409)
    return by_id


def _new_association(entry: ImportEntry) -> AssociationState:
    return (
        AssociationState.LINKED
        if entry.user_id is not None
        else AssociationState.UNRESOLVED
    )


def _apply_entries(
    org: Organization,
    event: Event,
    entries: list[ImportEntry],
    retained: dict[int, ExternalPromotionReceipt],
) -> tuple[list[Status], int]:
    """Write the validated batch. Runs inside the event lock."""
    statuses: list[Status] = []
    updated = 0
    now = timezone.now()
    for entry in entries:
        receipt = retained.get(entry.source_contact_id)
        if receipt is None:
            ExternalPromotionReceipt.objects.create(
                organization=org,
                source=ReceiptSource.CONTACT_LOG,
                source_contact_id=entry.source_contact_id,
                event=event,
                discord_id=entry.discord_id,
                recorded_at=entry.recorded_at,
                contact_method=entry.contact_method,
                linkage=entry.linkage,
                source_hash=entry.source_hash,
                first_imported_at=now,
                user_id=entry.user_id,
                org_user_id=entry.org_user_id,
                association_state=_new_association(entry),
                association_updated_at=now,
            )
            statuses.append("applied")
            continue
        outcome = reconcile_association(receipt, entry.user_id, entry.org_user_id)
        statuses.append(outcome.status)
        updated += outcome.association_updated
    return statuses, updated


def import_contact_receipts(org: Organization, payload: dict) -> dict[str, Any]:
    """Validate and store one batch atomically; see the module docstring.

    Raises ``IntegrationError``: 400 for any invalid or unauthorized entry,
    403/404 for binding problems, 409 ``mapping_changed`` for a stale
    ``mapping_version``, 409 ``source_content_conflict`` for changed
    source facts, 409 ``import_conflict_retry`` when a concurrent import
    stored one of the source IDs first, and 503 ``subject_source_unavailable``
    when the guild cannot be read. Nothing is written when it raises.
    """
    version, entries = _parse(payload)
    if not entries:
        get_org_binding(org.pk)
        return _result([], 0)
    event_id = entries[0].event_id
    get_event_binding(org.pk, event_id)
    # The guild read is network I/O; on SQLite the locked transaction below
    # holds the database-wide write lock, so it must happen first. Inside
    # the lock only the database sources and the version are re-checked.
    try:
        event = Event.objects.nocache().get(pk=event_id, organization=org)
    except Event.DoesNotExist:
        raise IntegrationError("not_found", 404) from None
    guild = guild_snapshot(org, event)

    def locked() -> dict[str, Any]:
        event = Event.objects.nocache().get(pk=event_id, organization=org)
        universe = authorized_event_subjects(org, event, guild=guild)
        if universe.mapping_version != version:
            raise IntegrationError("mapping_changed", 409)
        _authorize(universe, entries)
        retained = _retained(org, entries)
        statuses, updated = _apply_entries(org, event, entries, retained)
        return _result(statuses, updated)

    try:
        result = with_event_mutation(event_id, locked)
    except IntegrityError:
        # A concurrent import (for example of another event) stored one of
        # these source IDs first. The batch rolled back; a retry sees the
        # stored receipt and reports unchanged or source_content_conflict.
        log.warning(
            "integration_contacts_import_conflict",
            system="org",
            subsystem="integration",
            org_id=org.pk,
            event_id=event_id,
        )
        raise IntegrationError("import_conflict_retry", 409) from None
    log.info(
        "integration_contacts_imported",
        system="org",
        subsystem="integration",
        org_id=org.pk,
        event_id=event_id,
        applied=result["applied"],
        unchanged=result["unchanged"],
        quarantined=result["quarantined"],
        association_updated=result["association_updated"],
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
