"""Durable state for the event-promotion contact sync.

``ExternalPromotionReceipt`` is one contact of the bound guild recorded in
the external contact log. Its source facts, Discord IDs and event change
only inside ``ExternalPromotionReceipt.source_update()`` (the supersede path
in ``org.integration.points``); the DraftForge association (``user``,
``org_user``, ``association_*``) and the promotion-point state are updated
freely. It never becomes a ``PromoSend``; its point lives in the
contribution ledger.

``PromotionContactOutbox`` is one row per recorded ``PromoSend``, written in
the same transaction. It keeps the send's identity as scalars instead of
foreign keys so an undo or event cleanup cannot erase a pending receipt, and
it freezes the contracted payload and its hash once materialised.
"""

import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
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


class PromotionImportObservation(models.Model):
    """Newest committed source observation over a disjoint (after, through] span.

    Skipped source IDs are holes, not deletion observations. Import code keeps
    adjacent spans with the same timestamp coalesced under the org lock.
    """

    organization = models.ForeignKey("org.Organization", on_delete=models.CASCADE)
    source = models.CharField(max_length=32, default="contact_log")
    after = models.BigIntegerField()
    through = models.BigIntegerField()
    observed_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(through__gt=models.F("after")),
                name="promotion_observation_nonempty",
            ),
        ]


class PromotionSendExternalKey(models.Model):
    """A held Discord key merged into a send's recipient, even after a void.

    These identity links do not award or reverse points. They follow their
    send across later merges and disappear with it on undo or deletion.
    """

    send = models.ForeignKey(
        "org.PromoSend", on_delete=models.CASCADE, related_name="external_point_keys"
    )
    discord_id = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["send", "discord_id"], name="promotion_send_external_key_unique"
            ),
        ]


class ReceiptSource(models.TextChoices):
    CONTACT_LOG = "contact_log", "Contact log"


class ContactMethod(models.TextChoices):
    DISCORD_DM = "DISCORD_DM", "Discord DM"
    DISCORD_GROUP_DM = "DISCORD_GROUP_DM", "Discord group DM"
    OTHER = "OTHER", "Other"


class ContactReason(models.TextChoices):
    EVENT_INVITE = "EVENT_INVITE", "Event invite"
    FOLLOW_UP = "FOLLOW_UP", "Follow-up"
    GENERAL = "GENERAL", "General"


class PointStatus(models.TextChoices):
    """How an imported contact settled its (event, player) promotion point."""

    NOT_APPLICABLE = "not_applicable", "Not applicable"
    ECHO = "echo", "Echo of a local send"
    CREDITED = "credited", "Credited"
    UNCREDITED = "uncredited", "Uncredited"
    DUPLICATE = "duplicate", "Duplicate"
    RETRACTED = "retracted", "Retracted"


class PointReason(models.TextChoices):
    """Why a point-holding contact credits nobody."""

    NONE = "", "None"
    PROMOTER_UNRESOLVED = "promoter_unresolved", "Promoter unresolved"
    PROMOTER_UNMATCHED = "promoter_unmatched", "Promoter unmatched"
    PROMOTER_NOT_MEMBER = "promoter_not_member", "Promoter not a member"
    SELF_CONTACT = "self_contact", "Self contact"


HOLDING_STATUSES: tuple[str, ...] = (PointStatus.CREDITED, PointStatus.UNCREDITED)

# Set while ``ExternalPromotionReceipt.source_update()`` is active.
_SOURCE_UPDATE: ContextVar[bool] = ContextVar("receipt_source_update", default=False)


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
    """One contact of the bound guild recorded in the external contact log."""

    # Never change.
    IMMUTABLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "organization",
        "source",
        "source_contact_id",
        "first_imported_at",
    )
    # Change only inside ``source_update()``.
    SOURCE_FIELDS: ClassVar[tuple[str, ...]] = (
        "recorded_at",
        "contact_date_ny",
        "contact_method",
        "contact_reason",
        "occasion_id",
        "event_date",
        "forced",
        "source_hash",
        "discord_id",
        "promoter_discord_id",
        "event",
    )

    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="external_promotion_receipts",
    )
    source = models.CharField(max_length=16, choices=ReceiptSource.choices)
    source_contact_id = models.BigIntegerField()
    first_imported_at = models.DateTimeField(default=timezone.now)

    # Source facts (hashed into source_hash).
    recorded_at = models.DateTimeField()
    contact_date_ny = models.DateField()
    contact_method = models.CharField(max_length=24, choices=ContactMethod.choices)
    contact_reason = models.CharField(max_length=16, choices=ContactReason.choices)
    occasion_id = models.BigIntegerField(null=True, blank=True)
    event_date = models.DateTimeField(null=True, blank=True)
    forced = models.BooleanField(default=False)
    source_hash = models.CharField(max_length=64)

    # Derived identity: the target's and promoter's current primary Discord
    # accounts ("" promoter = unresolved), and the bound event.
    discord_id = models.CharField(max_length=20)
    promoter_discord_id = models.CharField(max_length=20, blank=True, default="")
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_promotion_receipts",
    )

    # Supersede and retraction audit.
    source_revision = models.PositiveIntegerField(default=0)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    retracted_at = models.DateTimeField(null=True, blank=True)
    # The newest source scan that observed this contact (present, edited or
    # deleted). An older scan cannot replace that observation.
    source_observed_at = models.DateTimeField(null=True, blank=True)

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

    # Promotion-point state, written by org.integration.points.
    point_status = models.CharField(
        max_length=16,
        choices=PointStatus.choices,
        default=PointStatus.NOT_APPLICABLE,
    )
    point_reason = models.CharField(
        max_length=24, choices=PointReason.choices, default=PointReason.NONE, blank=True
    )
    holds_point = models.BooleanField(default=False)
    origin_send_id = models.BigIntegerField(null=True, blank=True)

    objects = _GuardedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source", "source_contact_id"],
                name="uniq_external_promo_receipt_source_id",
            ),
            models.UniqueConstraint(
                fields=["organization", "event", "discord_id"],
                condition=models.Q(holds_point=True),
                name="uniq_external_promo_point",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(occasion_id__isnull=False, event_date__isnull=True)
                    | models.Q(occasion_id__isnull=True, event_date__isnull=False)
                ),
                name="ck_ext_promo_rcpt_occasion_xor_date",
            ),
            models.CheckConstraint(
                condition=models.Q(forced=False) | models.Q(occasion_id__isnull=False),
                name="ck_ext_promo_rcpt_forced_occasion",
            ),
            models.CheckConstraint(
                condition=models.Q(holds_point=False) | models.Q(event__isnull=False),
                name="ck_ext_promo_rcpt_point_has_event",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    holds_point=True, point_status__in=list(HOLDING_STATUSES)
                )
                | (
                    models.Q(holds_point=False)
                    & ~models.Q(point_status__in=list(HOLDING_STATUSES))
                ),
                name="ck_ext_promo_rcpt_point_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(retracted_at__isnull=True)
                    & ~models.Q(point_status=PointStatus.RETRACTED)
                )
                | models.Q(
                    retracted_at__isnull=False, point_status=PointStatus.RETRACTED
                ),
                name="ck_ext_promo_rcpt_retracted",
            ),
        ]
        indexes = [
            models.Index(
                fields=["event", "discord_id"], name="ext_promo_rcpt_event_discord"
            ),
            models.Index(
                fields=["organization", "discord_id", "recorded_at"],
                name="ext_promo_rcpt_org_discord_at",
            ),
            models.Index(
                fields=["organization", "contact_date_ny"],
                name="ext_promo_rcpt_org_date",
            ),
        ]

    @classmethod
    def frozen_field_names(cls) -> set[str]:
        if _SOURCE_UPDATE.get():
            return _model_fields(cls, cls.IMMUTABLE_FIELDS)
        return _model_fields(cls, cls.IMMUTABLE_FIELDS + cls.SOURCE_FIELDS)

    @staticmethod
    @contextmanager
    def source_update() -> Iterator[None]:
        """Allow writes to ``SOURCE_FIELDS`` for the duration of the block.

        Only the supersede path uses it, under the event lock. Identity
        fields (``IMMUTABLE_FIELDS``) stay frozen even here.
        """
        token = _SOURCE_UPDATE.set(True)
        try:
            yield
        finally:
            _SOURCE_UPDATE.reset(token)

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
    """The pending external receipt for one recorded promotion DM."""

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
