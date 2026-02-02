from django.db import models
from django.utils import timezone


class OrgUser(models.Model):
    """User's membership and MMR within an organization."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="org_memberships",
        db_index=True,
    )
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="members",
        db_index=True,
    )
    mmr = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    # MMR verification (moved from CustomUser)
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    @property
    def needs_mmr_verification(self) -> bool:
        """Check if MMR verification is needed (older than 30 days)."""
        if not self.has_active_dota_mmr:
            return False
        if self.dota_mmr_last_verified is None:
            return True
        days_since = (timezone.now() - self.dota_mmr_last_verified).days
        return days_since > 30

    class Meta:
        unique_together = ["user", "organization"]

    def __str__(self):
        return f"{self.user.username} @ {self.organization.name}"
