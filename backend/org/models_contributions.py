from django.core.validators import MaxLengthValidator
from django.db import models

from org.contributions.kinds import EVENT_STAFF_KINDS, RATED_KINDS, ContributionKind


class ContributionPointValue(models.Model):
    """Per-org override of a contribution kind's default points."""

    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="point_values",
    )
    kind = models.CharField(
        max_length=32, choices=[(k.value, k.label) for k in RATED_KINDS]
    )
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
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="contribution_entries",
    )
    kind = models.CharField(max_length=32, choices=ContributionKind.choices)
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
                condition=models.Q(kind__in=EVENT_STAFF_KINDS)
                & models.Q(event__isnull=False),
                name="uniq_event_staff_entry",
            ),
            models.UniqueConstraint(
                fields=["promo_send"],
                condition=models.Q(promo_send__isnull=False),
                name="uniq_entry_per_promo_send",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "occurred_at"]),
            models.Index(fields=["org_user", "occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} +{self.points} for org_user {self.org_user_id}"
