"""The per-DM promotion outbox: local writes only.

``record_promo_send`` calls ``enqueue_send`` inside its own transaction for
every send, earning or not, so the send, its award and its outbox row commit
or roll back together. Nothing here opens a connection or schedules a task;
dispatching to the adaptor happens later, outside any send transaction.

A send whose sender or recipient has no Discord ID cannot form a contracted
receipt. It still gets a row, in ``reconciliation_required`` with no
payload, so the DM is never lost and never dispatched with an invented ID.
"""

from __future__ import annotations

from typing import Any, Final

from org.integration.receipts import canonical_receipt_hash, format_timestamp
from org.models import OrgUser, PromoSend
from org.models_promotion_sync import OutboxState, PromotionContactOutbox
from telemetry.logging import get_logger

log = get_logger(__name__)

SCHEMA_VERSION: Final[int] = 1
SENDER_DISCORD_MISSING: Final[str] = "sender_discord_missing"
RECIPIENT_DISCORD_MISSING: Final[str] = "recipient_discord_missing"


def _id(value: int | None) -> str | None:
    return None if value is None else str(value)


def _missing_identity(send: PromoSend) -> str | None:
    if send.sender is None or not send.sender.discordId:
        return SENDER_DISCORD_MISSING
    if send.recipient is None or not send.recipient.discordId:
        return RECIPIENT_DISCORD_MISSING
    return None


def _payload(send: PromoSend, row: PromotionContactOutbox) -> dict[str, Any]:
    sender = send.sender
    recipient = send.recipient
    assert sender is not None and recipient is not None
    org_user_id = (
        OrgUser.objects.nocache()
        .filter(user=recipient, organization_id=send.organization_id)
        .values_list("pk", flat=True)
        .first()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "delivery_id": str(row.delivery_id),
        "org_id": str(send.organization_id),
        "event_id": str(send.event_id),
        "local_send_id": str(send.pk),
        "sender": {"user_id": str(sender.pk), "discord_id": sender.discordId},
        "recipient": {
            "user_id": str(recipient.pk),
            "org_user_id": _id(org_user_id),
            "discord_id": recipient.discordId,
        },
        "sent_at": format_timestamp(send.sent_at),
    }


def enqueue_send(send: PromoSend) -> PromotionContactOutbox:
    """The outbox row for ``send``, created on first call.

    Must run inside the transaction that created ``send``.
    """
    existing = PromotionContactOutbox.objects.filter(
        organization_id=send.organization_id, local_send_id=send.pk
    ).first()
    if existing is not None:
        return existing
    row = PromotionContactOutbox(
        organization_id=send.organization_id,
        local_send_id=send.pk,
        event_id=send.event_id,
        sender_user_id=send.sender_id,
        recipient_user_id=send.recipient_id,
        sent_at=send.sent_at,
    )
    missing = _missing_identity(send)
    if missing is None:
        row.payload = _payload(send, row)
        row.payload_hash = canonical_receipt_hash(row.payload)
        row.state = OutboxState.PENDING
        row.due_at = row.created_at
    else:
        row.state = OutboxState.RECONCILIATION_REQUIRED
        row.last_reason = missing
    row.save()
    log.info(
        "promo_outbox_enqueued",
        system="org",
        subsystem="integration",
        org_id=send.organization_id,
        event_id=send.event_id,
        send_id=send.pk,
        state=row.state,
        reason=row.last_reason or None,
    )
    return row


def outbox_summary(send_id: int, org_id: int) -> dict[str, str | None]:
    """The writeback state of one local send. Never implies an external write
    unless the row reached ``applied``."""
    row = (
        PromotionContactOutbox.objects.filter(
            organization_id=org_id, local_send_id=send_id
        )
        .values("state", "last_reason", "delivery_id")
        .first()
    )
    if row is None:
        return {"state": None, "reason": None, "delivery_id": None}
    return {
        "state": row["state"],
        "reason": row["last_reason"] or None,
        "delivery_id": str(row["delivery_id"]),
    }
