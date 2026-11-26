"""Settle the (event, player) promotion point an imported contact may hold.

One point exists per event and player Discord ID. An imported invitation
for a bound event settles it in this order:

- ``echo``: the external log recorded this contact on behalf of one of our
  sends (an applied outbox row names its source id). Nothing else happens.
- ``duplicate``: another imported contact already holds the point.
- otherwise the contact holds the point: ``credited`` when the external
  promoter's Discord ID belongs to a member of the org (a ``promo_message``
  ledger entry at the org's point value), else ``uncredited`` with the
  reason. A local send that earned the same point is then voided.

Every change is a ledger row, never a delete: a void is a ``promo_void``
reversing the entry (same ``occurred_at``, so monthly totals net to zero in
the right month), a restore is a ``promo_restore`` reversing the void, and
both are written to the org log. A contact that is superseded or retracted
releases its point to the lowest-id duplicate, or, with none left, restores
the local points it had voided.

Everything here runs inside the import's locks (the org row, then each
touched event in ascending order), so it does no locking of its own beyond
``select_for_update`` on a ledger entry before reading its points. The one
exception is ``settle_after_merge``, called by an account merge, which takes
the event locks itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from django.db.models import Q, QuerySet
from django.utils import timezone

from app.models import CustomUser
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.integration.event_lock import with_event_mutations
from org.models import ContributionEntry, OrgLog, OrgUser, PromoSend
from org.models_promotion_sync import (
    ContactReason,
    ExternalPromotionReceipt,
    OutboxState,
    PointReason,
    PointStatus,
    PromotionContactOutbox,
    PromotionSendExternalKey,
)
from org.standing import ledger
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from org.integration.contacts import ImportEntry

log = get_logger(__name__)

__all__ = [
    "PointOutcome",
    "external_point_held",
    "external_point_held_for",
    "resettle_key",
    "retract",
    "settle",
    "settle_after_merge",
    "supersede",
    "unsettle",
    "void_local",
]

CREDIT_REASON: Final[str] = "Recorded in the external contact log"
VOID_LOCAL_REASON: Final[str] = "Voided: the external contact log holds this point"
VOID_CREDIT_REASON: Final[str] = "Voided: the external contact changed or was removed"
RESTORE_REASON: Final[str] = "Restored: the external contact no longer holds this point"
_POINT_FIELDS: Final[list[str]] = [
    "point_status",
    "holds_point",
    "point_reason",
    "origin_send_id",
]


@dataclass(frozen=True)
class PointOutcome:
    """A receipt's ``point_status`` after settling, and what it did locally."""

    point: str
    voided_local: bool = False
    restored_local: int = 0


def _save_point(
    receipt: ExternalPromotionReceipt,
    status: str,
    *,
    holds: bool,
    reason: str = PointReason.NONE,
    origin_send_id: int | None = None,
) -> None:
    receipt.point_status = status
    receipt.holds_point = holds
    receipt.point_reason = reason
    receipt.origin_send_id = origin_send_id
    receipt.save(update_fields=_POINT_FIELDS)


def _eligible(receipt: ExternalPromotionReceipt) -> bool:
    return (
        receipt.contact_reason == ContactReason.EVENT_INVITE
        and receipt.event_id is not None
        and receipt.retracted_at is None
    )


def _echo_send_id(receipt: ExternalPromotionReceipt) -> int | None:
    return (
        PromotionContactOutbox.objects.filter(
            organization_id=receipt.organization_id,
            state=OutboxState.APPLIED,
            applied_contact_log_id=receipt.source_contact_id,
        )
        .values_list("local_send_id", flat=True)
        .first()
    )


def _key_receipts(
    org_id: int, event_id: int, discord_id: str
) -> QuerySet[ExternalPromotionReceipt]:
    return ExternalPromotionReceipt.objects.filter(
        organization_id=org_id, event_id=event_id, discord_id=discord_id
    )


def _promoter(receipt: ExternalPromotionReceipt) -> tuple[CustomUser | None, str]:
    """The member to credit, or ``None`` and the reason nobody is."""
    discord_id = receipt.promoter_discord_id
    if not discord_id:
        return None, PointReason.PROMOTER_UNRESOLVED
    if discord_id == receipt.discord_id:
        return None, PointReason.SELF_CONTACT
    user = CustomUser.objects.nocache().filter(discordId=discord_id).first()
    if user is None:
        return None, PointReason.PROMOTER_UNMATCHED
    member = (
        OrgUser.objects.nocache()
        .filter(user=user, organization_id=receipt.organization_id)
        .exists()
    )
    if not member:
        return None, PointReason.PROMOTER_NOT_MEMBER
    return user, PointReason.NONE


def _credit(receipt: ExternalPromotionReceipt, promoter: CustomUser) -> None:
    org = receipt.organization
    kind = ContributionKind.PROMO_MESSAGE.value
    ledger.award(
        org=org,
        user=promoter,
        kind=kind,
        occurred_at=receipt.recorded_at,
        points=ledger.points_for(org, kind),
        event=receipt.event,
        external_contact=receipt,
        reason=CREDIT_REASON,
        awarded_by=None,
    )


def settle(receipt: ExternalPromotionReceipt) -> PointOutcome:
    """Settle a ``not_applicable`` or ``uncredited`` receipt's point.

    Any other status is already settled and is returned as it is. A
    receipt that is not an invitation for a bound event, or is retracted,
    is ``not_applicable``.
    """
    status = receipt.point_status
    if status not in (PointStatus.NOT_APPLICABLE, PointStatus.UNCREDITED):
        return PointOutcome(status)
    if not _eligible(receipt):
        if status != PointStatus.NOT_APPLICABLE:
            _save_point(receipt, PointStatus.NOT_APPLICABLE, holds=False)
        return PointOutcome(PointStatus.NOT_APPLICABLE)
    if status == PointStatus.NOT_APPLICABLE:
        origin = _echo_send_id(receipt)
        if origin is not None:
            _save_point(receipt, PointStatus.ECHO, holds=False, origin_send_id=origin)
            return PointOutcome(PointStatus.ECHO)
        assert receipt.event_id is not None
        held = (
            _key_receipts(receipt.organization_id, receipt.event_id, receipt.discord_id)
            .filter(holds_point=True)
            .exclude(pk=receipt.pk)
            .exists()
        )
        if held:
            _save_point(receipt, PointStatus.DUPLICATE, holds=False)
            return PointOutcome(PointStatus.DUPLICATE)
    promoter, reason = _promoter(receipt)
    if promoter is None:
        _save_point(receipt, PointStatus.UNCREDITED, holds=True, reason=reason)
    else:
        _save_point(receipt, PointStatus.CREDITED, holds=True)
        _credit(receipt, promoter)
    return PointOutcome(receipt.point_status, voided_local=void_local(receipt))


def _key_sends(event_id: int, discord_id: str) -> QuerySet[PromoSend]:
    """Sends of the event to this Discord ID: by the send-time snapshot, or
    by the recipient's current account for rows recorded without one."""
    return PromoSend.objects.filter(event_id=event_id).filter(
        Q(recipient_discord_id=discord_id)
        | Q(recipient_discord_id="", recipient__discordId=discord_id)
    )


def _locked_entry(**filters: Any) -> ContributionEntry | None:
    return (
        ContributionEntry.objects.nocache()
        .select_for_update()
        .filter(**filters)
        .first()
    )


def _reverse(
    entry: ContributionEntry,
    *,
    kind: ContributionKind,
    points: int,
    receipt: ExternalPromotionReceipt,
    reason: str,
) -> ContributionEntry:
    reversal = ContributionEntry.objects.create(
        org_user_id=entry.org_user_id,
        organization_id=entry.organization_id,
        track="contribution",
        kind=kind.value,
        points=points,
        event_id=entry.event_id,
        event_name=entry.event_name,
        occurred_at=entry.occurred_at,
        reversal_of=entry,
        external_contact=receipt,
        # Freeze the external key that displaced a local send; the receipt's
        # target can change later.
        external_point_discord_id=(
            receipt.discord_id
            if kind == ContributionKind.PROMO_VOID and entry.promo_send_id is not None
            else ""
        ),
        reason=reason,
    )
    entry.voided = kind == ContributionKind.PROMO_VOID
    entry.save(update_fields=["voided", "updated_at"])
    return reversal


def _audit(
    receipt: ExternalPromotionReceipt,
    action: str,
    *,
    target: CustomUser | None,
    details: dict[str, Any],
) -> None:
    OrgLog.objects.create(
        organization_id=receipt.organization_id,
        actor=None,
        action=action,
        target_user=target,
        details=details,
    )


def _void(
    entry: ContributionEntry,
    receipt: ExternalPromotionReceipt,
    *,
    reason: str,
    target: CustomUser | None,
    send_id: int | None,
) -> None:
    void = _reverse(
        entry,
        kind=ContributionKind.PROMO_VOID,
        points=-entry.points,
        receipt=receipt,
        reason=reason,
    )
    _audit(
        receipt,
        "void_promo_point",
        target=target,
        details={
            "entry_pk": entry.pk,
            "void_pk": void.pk,
            "send_id": send_id,
            "event_id": entry.event_id,
            "source_contact_id": receipt.source_contact_id,
        },
    )
    log.info(
        "promo_point_voided",
        system="org",
        subsystem="integration",
        org_id=receipt.organization_id,
        event_id=entry.event_id,
        receipt_id=receipt.pk,
        entry_id=entry.pk,
        void_id=void.pk,
        send_id=send_id,
    )


def void_local(receipt: ExternalPromotionReceipt) -> bool:
    """Void the local point for the receipt's (event, player), if any.

    The earning send stops earning and its entry gets a ``promo_void``; the
    send, its outbox row and its tick stay. True when an entry was voided.
    """
    if not receipt.holds_point or receipt.event_id is None:
        return False
    voided = False
    sends = (
        _key_sends(receipt.event_id, receipt.discord_id)
        .filter(earns_points=True)
        .select_related("sender")
        .order_by("pk")
    )
    for send in sends:
        send.earns_points = False
        send.save(update_fields=["earns_points"])
        entry = _locked_entry(promo_send=send)
        if entry is None or entry.voided:
            continue
        _void(
            entry,
            receipt,
            reason=VOID_LOCAL_REASON,
            target=send.sender,
            send_id=send.pk,
        )
        voided = True
    return voided


def unsettle(receipt: ExternalPromotionReceipt) -> None:
    """Void the receipt's live credit and release its point.

    Local points it voided stay voided; ``resettle_key`` decides them.
    """
    credits = (
        ContributionEntry.objects.nocache()
        .select_for_update()
        .filter(
            external_contact=receipt,
            kind=ContributionKind.PROMO_MESSAGE.value,
            voided=False,
        )
        .select_related("org_user")
        .order_by("pk")
    )
    for credit in credits:
        _void(
            credit,
            receipt,
            reason=VOID_CREDIT_REASON,
            target=credit.org_user.user,
            send_id=None,
        )
    _save_point(receipt, PointStatus.NOT_APPLICABLE, holds=False)


def _changes(receipt: ExternalPromotionReceipt, values: dict[str, Any]) -> list[str]:
    changed = []
    for name, value in values.items():
        if name == "event":
            if receipt.event_id != (value.pk if value is not None else None):
                changed.append(name)
        elif getattr(receipt, name) != value:
            changed.append(name)
    return changed


def supersede(
    receipt: ExternalPromotionReceipt, new: ImportEntry, event: Event | None
) -> PointOutcome:
    """Replace the receipt's source facts and identity with ``new`` and
    settle again, releasing the old (event, player) key if it moved.

    ``restored_local`` counts local points restored on the old key.
    """
    old_event_id, old_discord_id = receipt.event_id, receipt.discord_id
    old_hash = receipt.source_hash
    unsettle(receipt)
    values: dict[str, Any] = {
        "recorded_at": new.recorded_at,
        "contact_date_ny": new.contact_date_ny,
        "contact_method": new.contact_method,
        "contact_reason": new.contact_reason,
        "occasion_id": new.occasion_id,
        "event_date": new.event_date,
        "forced": new.forced,
        "source_hash": new.source_hash,
        "discord_id": new.target_discord_id,
        "promoter_discord_id": new.promoter_discord_id or "",
        "event": event,
    }
    changed = _changes(receipt, values)
    for name, value in values.items():
        setattr(receipt, name, value)
    receipt.source_revision += 1
    receipt.source_updated_at = timezone.now()
    with ExternalPromotionReceipt.source_update():
        receipt.save(update_fields=[*values, "source_revision", "source_updated_at"])
    _audit(
        receipt,
        "update_external_contact",
        target=None,
        details={
            "source_contact_id": receipt.source_contact_id,
            "revision": receipt.source_revision,
            "old_hash": old_hash,
            "new_hash": receipt.source_hash,
            "changed": changed,
            "old_event_id": old_event_id,
            "new_event_id": receipt.event_id,
        },
    )
    outcome = settle(receipt)
    restored = 0
    kept = receipt.holds_point and (receipt.event_id, receipt.discord_id) == (
        old_event_id,
        old_discord_id,
    )
    if old_event_id is not None and not kept:
        restored = resettle_key(old_event_id, old_discord_id, released_by=receipt)
    return PointOutcome(outcome.point, outcome.voided_local, restored)


def retract(receipt: ExternalPromotionReceipt) -> int:
    """Mark a receipt deleted at the source and release its point.

    Returns the number of local points restored.
    """
    event_id, discord_id = receipt.event_id, receipt.discord_id
    unsettle(receipt)
    receipt.retracted_at = timezone.now()
    receipt.point_status = PointStatus.RETRACTED
    receipt.save(update_fields=["retracted_at", "point_status"])
    if event_id is None:
        return 0
    return resettle_key(event_id, discord_id, released_by=receipt)


def resettle_key(
    event_id: int, discord_id: str, *, released_by: ExternalPromotionReceipt
) -> int:
    """Settle a released (event, player) point again.

    The lowest-id duplicate takes it over (local points stay voided: the
    point is still external). With no duplicate left, every voided local
    point of the key is restored. Returns the number restored.
    """
    receipts = _key_receipts(released_by.organization_id, event_id, discord_id)
    while not receipts.filter(holds_point=True).exists():
        nxt = (
            receipts.filter(point_status=PointStatus.DUPLICATE)
            .order_by("source_contact_id")
            .first()
        )
        if nxt is None:
            return _restore_local(event_id, discord_id, released_by)
        _save_point(nxt, PointStatus.NOT_APPLICABLE, holds=False)
        settle(nxt)
    return 0


def _restore_local(
    event_id: int, discord_id: str, receipt: ExternalPromotionReceipt
) -> int:
    # A merge can put a send under a different Discord ID than the
    # external key that voided it. Follow the reversal's frozen key, not
    # the receipt's current target (supersede may already have changed it).
    voided_sends = ContributionEntry.objects.filter(
        kind=ContributionKind.PROMO_VOID.value,
        event_id=event_id,
        organization_id=receipt.organization_id,
        external_point_discord_id=discord_id,
        reversal_of__voided=True,
    ).values("reversal_of__promo_send_id")
    linked_sends = PromotionSendExternalKey.objects.filter(
        discord_id=discord_id, send__event_id=event_id
    ).values("send_id")
    candidates = PromoSend.objects.filter(event_id=event_id).filter(
        Q(pk__in=_key_sends(event_id, discord_id).values("pk"))
        | Q(pk__in=voided_sends)
        | Q(pk__in=linked_sends)
    )
    restored = 0
    for send in candidates.select_related("sender").order_by("pk"):
        entry = _locked_entry(promo_send=send)
        if entry is None or not entry.voided:
            continue
        # Another external key may still hold the merged recipient's
        # point. A second earning local send must not be credited either.
        if external_point_held_for(event_id, send.recipient_id) or (
            PromoSend.objects.filter(
                event_id=event_id, recipient_id=send.recipient_id, earns_points=True
            )
            .exclude(pk=send.pk)
            .exists()
        ):
            continue
        void = entry.reversals.filter(kind=ContributionKind.PROMO_VOID.value).last()
        restore = _reverse(
            entry,
            kind=ContributionKind.PROMO_RESTORE,
            points=-void.points if void is not None else entry.points,
            receipt=receipt,
            reason=RESTORE_REASON,
        )
        _audit(
            receipt,
            "restore_promo_point",
            target=send.sender,
            details={
                "entry_pk": entry.pk,
                "restore_pk": restore.pk,
                "send_id": send.pk,
                "event_id": event_id,
                "source_contact_id": receipt.source_contact_id,
            },
        )
        send.earns_points = True
        send.save(update_fields=["earns_points"])
        log.info(
            "promo_point_restored",
            system="org",
            subsystem="integration",
            org_id=receipt.organization_id,
            event_id=event_id,
            receipt_id=receipt.pk,
            entry_id=entry.pk,
            restore_id=restore.pk,
            send_id=send.pk,
        )
        restored += 1
    return restored


def external_point_held(event: Event, recipient: CustomUser) -> bool:
    """Whether an imported contact holds the point for this recipient.

    True when a receipt in any association state holds the point for the
    recipient's current Discord ID or a send-time Discord ID of their sends
    for the event, or for the external key frozen on a void of one of their
    entries. A merge can bring that send to an account with another Discord
    ID, and a duplicate may replace the original holder. This is the one
    predicate behind "may send", "will earn" and the tick.
    """
    return external_point_held_for(event.pk, recipient.pk)


def external_point_held_for(event_id: int, recipient_id: int) -> bool:
    """``external_point_held`` by ids, in one query."""
    snapshots = (
        PromoSend.objects.filter(event_id=event_id, recipient_id=recipient_id)
        .exclude(recipient_discord_id="")
        .values("recipient_discord_id")
    )
    current = (
        CustomUser.objects.filter(pk=recipient_id)
        .exclude(discordId__isnull=True)
        .exclude(discordId="")
        .values("discordId")
    )
    voided_keys = (
        ContributionEntry.objects.filter(
            kind=ContributionKind.PROMO_VOID.value,
            reversal_of__voided=True,
            reversal_of__promo_send__event_id=event_id,
            reversal_of__promo_send__recipient_id=recipient_id,
        )
        .exclude(external_point_discord_id="")
        .values("external_point_discord_id")
    )
    linked_keys = PromotionSendExternalKey.objects.filter(
        send__event_id=event_id, send__recipient_id=recipient_id
    ).values("discord_id")
    return (
        ExternalPromotionReceipt.objects.filter(event_id=event_id, holds_point=True)
        .filter(
            Q(discord_id__in=snapshots)
            | Q(discord_id__in=current)
            | Q(discord_id__in=voided_keys)
            | Q(discord_id__in=linked_keys)
        )
        .exists()
    )


def settle_after_merge(keep: CustomUser, discord_ids: set[str]) -> int:
    """Void ``keep``'s earning sends on points an imported contact holds.

    Runs inside the merge transaction once the sends have moved to
    ``keep``. ``discord_ids`` are both accounts' Discord IDs, read before
    the merge. For every event where a receipt with one of them holds the
    point, every ``keep`` send for that event records the held Discord IDs,
    even when an earlier merge already voided it. Earning sends then stop
    earning and their entries are voided as ``void_local`` does, under the
    event locks in ascending order. Returns the number of entries voided.
    """
    ids = {d for d in discord_ids if d}
    if not ids:
        return 0
    held = set(
        ExternalPromotionReceipt.objects.filter(
            discord_id__in=ids, holds_point=True, event__isnull=False
        ).values_list("event_id", flat=True)
    )
    if not held:
        return 0
    touched = set(
        PromoSend.objects.filter(recipient=keep, event_id__in=held).values_list(
            "event_id", flat=True
        )
    )
    if not touched:
        return 0

    def locked() -> int:
        voided = 0
        for event_id in sorted(touched):
            holders = list(
                ExternalPromotionReceipt.objects.filter(
                    event_id=event_id, discord_id__in=ids, holds_point=True
                ).order_by("source_contact_id")
            )
            if not holders:
                continue
            holder = holders[0]
            # Identity survives even when a previous merge already voided
            # the send. This is not another ledger reversal.
            send_ids = list(
                PromoSend.objects.filter(event_id=event_id, recipient=keep).values_list(
                    "pk", flat=True
                )
            )
            PromotionSendExternalKey.objects.bulk_create(
                [
                    PromotionSendExternalKey(send_id=send_id, discord_id=key)
                    for send_id in send_ids
                    for key in {r.discord_id for r in holders}
                ],
                ignore_conflicts=True,
            )
            sends = (
                PromoSend.objects.filter(
                    event_id=event_id, recipient=keep, earns_points=True
                )
                .select_related("sender")
                .order_by("pk")
            )
            for send in sends:
                send.earns_points = False
                send.save(update_fields=["earns_points"])
                entry = _locked_entry(promo_send=send)
                if entry is None or entry.voided:
                    continue
                _void(
                    entry,
                    holder,
                    reason=VOID_LOCAL_REASON,
                    target=send.sender,
                    send_id=send.pk,
                )
                voided += 1
        return voided

    voided = with_event_mutations(sorted(touched), locked)
    if voided:
        log.info(
            "promo_points_settled_after_merge",
            system="org",
            subsystem="integration",
            keep_user_id=keep.pk,
            events=len(touched),
            voided=voided,
        )
    return voided
