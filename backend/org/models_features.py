from django.db import models

from org.feature_keys import FeatureKey


class OrgFeature(models.Model):
    """Paid feature switch for one organization, unlocked by a site admin."""

    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="features",
    )
    feature = models.CharField(max_length=32, choices=FeatureKey.choices)
    enabled = models.BooleanField(default=False)
    enabled_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    enabled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "feature"], name="uniq_org_feature"
            ),
        ]

    def __str__(self) -> str:
        state = "on" if self.enabled else "off"
        return f"{self.feature} ({state}) @ org {self.organization_id}"
