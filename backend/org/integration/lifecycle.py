"""Keep imported SFG receipts honest across account merges and deletions.

A receipt is evidence that SFG recorded a contact with one Discord ID. When
accounts change, the evidence stays and only its DraftForge association
moves, and only to the account that owns that Discord ID:

- ``reconcile_promotion_identity(keep, drop)`` runs before ``drop`` is
  folded into ``keep``. Receipts linked to ``drop`` move to ``keep`` when
  ``keep`` owns their Discord ID (with ``keep``'s membership in that org);
  otherwise they are quarantined, unlinked, so the generic merge cannot
  hand the tick to a different Discord owner. Outbox rows that are not yet
  applied or canceled and name ``drop`` as sender or recipient are pointed at
  ``keep``, following the sends the merge moves, so the delete hook that
  runs for ``drop`` finds nothing of the merged account's to cancel. Their
  frozen payloads keep the identity recorded at send time.
- ``cancel_or_redact_promotion_identity(user)`` runs before an account is
  deleted, from a ``pre_delete`` receiver in ``org.signals`` so no delete
  path can skip it. Its receipts are quarantined as ``account_deleted`` and
  unlinked, so a later replay of the same SFG contact neither ticks a new
  owner nor recreates anything. Its outbox rows that were never sent are
  canceled; applied, canceled and in-flight rows are left alone, and frozen
  payloads are not rewritten here.

Neither function creates an account or membership, touches source facts or
deletes a receipt.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from app.models import CustomUser
from org.models import OrgUser
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ExternalPromotionReceipt,
    OutboxState,
    PromotionContactOutbox,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

ACCOUNT_DELETED = "account_deleted"
_UNSENT_STATES = (
    OutboxState.PENDING,
    OutboxState.RETRY,
    OutboxState.PAUSED,
    OutboxState.RECONCILIATION_REQUIRED,
)
_OPEN_STATES = (*_UNSENT_STATES, OutboxState.IN_FLIGHT)
_ASSOCIATION_FIELDS = [
    "user",
    "org_user",
    "association_state",
    "association_reason",
    "association_updated_at",
]


def reconcile_promotion_identity(keep: CustomUser, drop: CustomUser) -> None:
    if keep.pk == drop.pk:
        return
    now = timezone.now()
    moved = quarantined = 0
    receipts = ExternalPromotionReceipt.objects.filter(user=drop)
    for receipt in receipts:
        verified = (
            bool(keep.discordId)
            and keep.discordId == receipt.discord_id
            and receipt.association_state != AssociationState.QUARANTINED
        )
        if verified:
            receipt.user = keep
            receipt.org_user = (
                OrgUser.objects.nocache()
                .filter(user=keep, organization_id=receipt.organization_id)
                .first()
            )
            receipt.association_state = AssociationState.LINKED
            receipt.association_reason = AssociationReason.NONE
            moved += 1
        else:
            receipt.user = None
            receipt.org_user = None
            if receipt.association_state != AssociationState.QUARANTINED:
                receipt.association_state = AssociationState.QUARANTINED
                receipt.association_reason = AssociationReason.DISCORD_OWNER_CHANGED
            quarantined += 1
        receipt.association_updated_at = now
        receipt.save(update_fields=_ASSOCIATION_FIELDS)
    senders, recipients = PromotionContactOutbox.objects.filter(
        state__in=_OPEN_STATES
    ).reassign_account(drop.pk, keep.pk)
    if moved or quarantined or senders or recipients:
        log.info(
            "promo_receipts_reconciled_for_merge",
            system="org",
            subsystem="integration",
            keep_user_id=keep.pk,
            drop_user_id=drop.pk,
            moved=moved,
            quarantined=quarantined,
            outbox_senders_moved=senders,
            outbox_recipients_moved=recipients,
        )


def cancel_or_redact_promotion_identity(user: CustomUser) -> None:
    now = timezone.now()
    quarantined = ExternalPromotionReceipt.objects.filter(user=user).update(
        user=None,
        org_user=None,
        association_state=AssociationState.QUARANTINED,
        association_reason=AssociationReason.ACCOUNT_DELETED,
        association_updated_at=now,
    )
    canceled = PromotionContactOutbox.objects.filter(
        Q(sender_user_id=user.pk) | Q(recipient_user_id=user.pk),
        state__in=_UNSENT_STATES,
    ).update(
        state=OutboxState.CANCELED,
        last_reason=ACCOUNT_DELETED,
        due_at=None,
        updated_at=now,
    )
    if quarantined or canceled:
        log.info(
            "promo_identity_canceled_for_deletion",
            system="org",
            subsystem="integration",
            user_id=user.pk,
            receipts_quarantined=quarantined,
            outbox_canceled=canceled,
        )
