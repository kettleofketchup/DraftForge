"""Durable state for the SFG event-promotion sync.

``ExternalPromotionReceipt`` is a contact some other system (SFG) recorded
for an event. Its source facts and ``source_hash`` never change after
import; only the DraftForge association (``user``, ``org_user``,
``association_*``) is updated. It is suppression evidence, never a
``PromoSend`` or a contribution award.

``PromotionContactOutbox`` is one row per recorded ``PromoSend``, written in
the same transaction. It keeps the send's identity as scalars instead of
foreign keys so an undo or event cleanup cannot erase a pending receipt, and
it freezes the contracted payload and its hash once materialised.
"""

import uuid
from collections.abc import Iterable
from typing import Any, ClassVar

from django.db import models
from django.utils import timezone


class ImmutableFieldError(ValueError):
    """An attempt to rewrite a field that is frozen once stored."""

    def __init__(self, model: str, fields: Iterable[str]) -> None:
        names = ", ".join(sorted(fields))
        super().__init__(f"{model} fields are immutable: {names}")


def _model_fields(model: type[models.Model], names: Iterable[str]) -> set[str]:
    """Field names plus their attnames (``user`` and ``user_id``)."""
    out: set[str] = set()
    for name in names:
        field = model._meta.get_field(name)
        out.update({field.name, field.attname})
    return out


class _GuardedQuerySet(models.QuerySet):
    """Refuses queryset writes to the model's frozen fields."""

    def update(self, **kwargs: Any) -> int:
        frozen = set(kwargs) & self.model.frozen_field_names()
        if frozen:
            raise ImmutableFieldError(self.model.__name__, frozen)
        return super().update(**kwargs)

    def bulk_update(
        self, objs: Any, fields: Iterable[str], *args: Any, **kw: Any
    ) -> int:
        fields = list(fields)
        frozen = set(fields) & self.model.frozen_field_names()
        if frozen:
            raise ImmutableFieldError(self.model.__name__, frozen)
        return super().bulk_update(objs, fields, *args, **kw)


class _OutboxQuerySet(_GuardedQuerySet):
    def reassign_account(self, drop_pk: int, keep_pk: int) -> tuple[int, int]:
        """Point these rows' sender and recipient IDs at ``keep_pk`` where
        they name ``drop_pk``. Returns (senders moved, recipients moved).

        The only sanctioned write to those IDs: an account merge folds the
        dropped account's sends into the kept one, and the outbox row must
        follow its send so the drop's delete hook cannot cancel it. Payloads
        are not touched.
        """
        now = timezone.now()
        # models.QuerySet.update skips the frozen-field guard on purpose.
        senders = models.QuerySet.update(
            self.filter(sender_user_id=drop_pk), sender_user_id=keep_pk, updated_at=now
        )
        recipients = models.QuerySet.update(
            self.filter(recipient_user_id=drop_pk),
            recipient_user_id=keep_pk,
            updated_at=now,
        )
        return senders, recipients

    def redact_payloads(self) -> int:
        """Drop these rows' frozen payloads, keeping ``payload_hash``.

        The only sanctioned write to ``payload`` after it is set: account
        deletion removes the Discord IDs it holds. The hash stays as a
        tombstone, and because it is non-empty the payload can never be
        materialised again.
        """
        # models.QuerySet.update skips the frozen-field guard on purpose.
        return models.QuerySet.update(
            self.filter(payload__isnull=False), payload=None, updated_at=timezone.now()
        )


class ReceiptSource(models.TextChoices):
    SFG = "sfg", "SFG"


class ContactMethod(models.TextChoices):
    DISCORD_DM = "DISCORD_DM", "Discord DM"
    DISCORD_GROUP_DM = "DISCORD_GROUP_DM", "Discord group DM"
    OTHER = "OTHER", "Other"


class ContactLinkage(models.TextChoices):
    OCCASION = "occasion", "Occasion"
    EVENT_DATE = "event_date", "Event date"


class AssociationState(models.TextChoices):
    UNRESOLVED = "unresolved", "Unresolved"
    LINKED = "linked", "Linked"
    QUARANTINED = "quarantined", "Quarantined"


class AssociationReason(models.TextChoices):
    """Fixed, value-free explanations for the current association."""

    NONE = "", "None"
    DISCORD_OWNER_CHANGED = (
        "discord_owner_changed",
        "Discord ID owned by another account",
    )
    ORG_USER_MISMATCH = "org_user_mismatch", "Membership of another account"
    ACCOUNT_DELETED = "account_deleted", "Account deleted"


class ExternalPromotionReceipt(models.Model):
    """One contact recorded by an external source for an event."""

    IMMUTABLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "organization",
        "source",
        "source_contact_id",
        "event",
        "discord_id",
        "recorded_at",
        "contact_method",
        "linkage",
        "source_hash",
        "first_imported_at",
    )

    # Immutable source facts.
    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="external_promotion_receipts",
    )
    source = models.CharField(max_length=16, choices=ReceiptSource.choices)
    source_contact_id = models.BigIntegerField()
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="external_promotion_receipts",
    )
    discord_id = models.CharField(max_length=20)
    recorded_at = models.DateTimeField()
    contact_method = models.CharField(max_length=24, choices=ContactMethod.choices)
    linkage = models.CharField(max_length=16, choices=ContactLinkage.choices)
    source_hash = models.CharField(max_length=64)
    first_imported_at = models.DateTimeField(default=timezone.now)

    # Mutable DraftForge association.
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_promotion_receipts",
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_promotion_receipts",
    )
    association_state = models.CharField(
        max_length=16,
        choices=AssociationState.choices,
        default=AssociationState.UNRESOLVED,
    )
    association_reason = models.CharField(
        max_length=32,
        choices=AssociationReason.choices,
        default=AssociationReason.NONE,
        blank=True,
    )
    association_updated_at = models.DateTimeField(null=True, blank=True)

    objects = _GuardedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source", "source_contact_id"],
                name="uniq_external_promo_receipt_source_id",
            ),
        ]
        indexes = [
            models.Index(
                fields=["event", "discord_id"], name="ext_promo_rcpt_event_discord"
            ),
        ]

    @classmethod
    def frozen_field_names(cls) -> set[str]:
        return _model_fields(cls, cls.IMMUTABLE_FIELDS)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            if update_fields is None:
                raise ImmutableFieldError(
                    type(self).__name__, ["(save without update_fields)"]
                )
            frozen = set(update_fields) & self.frozen_field_names()
            if frozen:
                raise ImmutableFieldError(type(self).__name__, frozen)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.source} contact {self.source_contact_id} @ org {self.organization_id}"


class OutboxState(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_FLIGHT = "in_flight", "In flight"
    RETRY = "retry", "Retry"
    PAUSED = "paused", "Paused"
    RECONCILIATION_REQUIRED = "reconciliation_required", "Reconciliation required"
    APPLIED = "applied", "Applied"
    CANCELED = "canceled", "Canceled"


class PromotionContactOutbox(models.Model):
    """The pending SFG receipt for one recorded promotion DM."""

    IMMUTABLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "organization",
        "local_send_id",
        "delivery_id",
        "event_id",
        "sender_user_id",
        "recipient_user_id",
        "sent_at",
        "created_at",
    )
    # Written once, when the receipt identity is complete.
    FROZEN_ONCE_SET: ClassVar[tuple[str, ...]] = ("payload", "payload_hash")

    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="promotion_contact_outbox",
    )
    # Scalars, not foreign keys: the receipt outlives undo and event cleanup.
    local_send_id = models.BigIntegerField()
    event_id = models.BigIntegerField(db_index=True)
    sender_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    recipient_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField()
    delivery_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    payload = models.JSONField(null=True, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True, default="")

    state = models.CharField(
        max_length=24, choices=OutboxState.choices, default=OutboxState.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    due_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_reason = models.CharField(max_length=64, blank=True, default="")
    applied_contact_log_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = _OutboxQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "local_send_id"],
                name="uniq_promo_outbox_local_send",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "due_at"], name="promo_outbox_state_due"),
        ]

    @classmethod
    def frozen_field_names(cls) -> set[str]:
        return _model_fields(cls, cls.IMMUTABLE_FIELDS + cls.FROZEN_ONCE_SET)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            self._guard_update(kwargs.get("update_fields"))
        super().save(*args, **kwargs)

    def _guard_update(self, update_fields: Iterable[str] | None) -> None:
        name = type(self).__name__
        if update_fields is None:
            raise ImmutableFieldError(name, ["(save without update_fields)"])
        fields = set(update_fields)
        frozen = fields & _model_fields(type(self), self.IMMUTABLE_FIELDS)
        if frozen:
            raise ImmutableFieldError(name, frozen)
        once = fields & _model_fields(type(self), self.FROZEN_ONCE_SET)
        if once:
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("payload_hash", flat=True)
                .first()
            )
            if stored:
                raise ImmutableFieldError(name, once)

    def __str__(self) -> str:
        return f"promo outbox send {self.local_send_id} @ org {self.organization_id}"
