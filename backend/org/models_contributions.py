from django.core.validators import MaxLengthValidator
from django.db import models

from org.standing.kinds import ONCE_PER_EVENT_KINDS


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
