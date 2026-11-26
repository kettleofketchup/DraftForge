from django.core.validators import MaxLengthValidator
from django.db import models

from org.contributions.kinds import REVERSAL_KINDS, ContributionKind
from org.standing.kinds import ONCE_PER_EVENT_KINDS

_REVERSALS = sorted(kind.value for kind in REVERSAL_KINDS)


class ContributionPointValue(models.Model):
    """Per-org override of a contribution kind's default points."""

    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="point_values",
    )
    kind = models.CharField(max_length=32)
    points = models.PositiveIntegerField()
    updated_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"], name="uniq_org_point_value"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}={self.points} @ org {self.organization_id}"


class ContributionEntry(models.Model):
    """One ledger row: points a member earned in an organization."""

    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.RESTRICT,
        related_name="contribution_entries",
    )
    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="contribution_entries",
    )
    track = models.CharField(max_length=32, default="contribution")
    kind = models.CharField(max_length=32)
    points = models.IntegerField()
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contribution_entries",
    )
    event_name = models.CharField(max_length=255, blank=True, default="")
    promo_send = models.ForeignKey(
        "org.PromoSend",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contribution_entries",
    )
    reason = models.TextField(
        blank=True, default="", validators=[MaxLengthValidator(500)]
    )
    awarded_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # The imported external contact behind an external credit, or behind a
    # void or restore an import caused.
    external_contact = models.ForeignKey(
        "org.ExternalPromotionReceipt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    # The external (event, Discord ID) key at the time a local point was
    # voided. The receipt's target may later change; the reversal must keep
    # the identity that displaced this send, including across merges.
    external_point_discord_id = models.CharField(max_length=20, blank=True, default="")
    # Set only on promo_void/promo_restore rows. CASCADE keeps the net at
    # zero when the reversed entry itself is deleted (an undone send).
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reversals",
    )
    # True while the entry's voids outnumber its restores.
    voided = models.BooleanField(default=False)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "org_user", "kind"],
                condition=models.Q(kind__in=sorted(ONCE_PER_EVENT_KINDS))
                & models.Q(event__isnull=False),
                name="uniq_event_once_entry",
            ),
            models.UniqueConstraint(
                fields=["promo_send"],
                condition=models.Q(promo_send__isnull=False),
                name="uniq_entry_per_promo_send",
            ),
            models.UniqueConstraint(
                fields=["external_contact"],
                condition=models.Q(kind=ContributionKind.PROMO_MESSAGE.value)
                & models.Q(external_contact__isnull=False)
                & models.Q(voided=False),
                name="uniq_external_promo_credit",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=_REVERSALS, reversal_of__isnull=False)
                | (~models.Q(kind__in=_REVERSALS) & models.Q(reversal_of__isnull=True)),
                name="ck_promo_reversal_link",
            ),
            models.CheckConstraint(
                condition=~models.Q(kind__in=_REVERSALS, voided=True),
                name="ck_promo_reversal_not_voided",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "track", "occurred_at"],
                name="ledger_org_track_at_idx",
            ),
            models.Index(
                fields=["org_user", "track", "occurred_at"],
                name="ledger_mbr_track_at_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} +{self.points} for org_user {self.org_user_id}"
