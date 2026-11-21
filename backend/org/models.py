from django.db import models
from django.utils import timezone

from common.game import GameType
from org.models_contributions import (
    ContributionEntry,  # noqa: F401
    ContributionPointValue,  # noqa: F401
)
from org.models_features import OrgFeature  # noqa: F401
from org.models_profiles import (
    PlayerDeadlockProfile,  # noqa: F401
    PlayerDotaProfile,  # noqa: F401
)
from org.models_promotion import (
    PromoSend,  # noqa: F401
    PromoTemplate,  # noqa: F401
)
from org.models_settings import OrgSettings  # noqa: F401


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
    guild_nickname = models.TextField(null=True, blank=True)
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

    def __str__(self) -> str:
        return f"{self.user.username} @ {self.organization.name}"


class OrgUserGameMmr(models.Model):
    """Org-assigned MMR for one game; a missing row means 0."""

    org_user = models.ForeignKey(
        OrgUser, on_delete=models.CASCADE, related_name="game_mmrs"
    )
    game_type = models.PositiveSmallIntegerField()
    mmr = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_user", "game_type"], name="org_user_game_mmr_unique"
            )
        ]

    def __str__(self) -> str:
        game = (
            GameType(self.game_type).label
            if self.game_type in GameType.values
            else str(self.game_type)
        )
        return f"{self.org_user_id} {game}: {self.mmr}"
