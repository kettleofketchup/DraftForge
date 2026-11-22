from django.conf import settings
from django.db import models
from django.utils import timezone

from app.cache_utils import invalidate_obj
from common.game import GameType
from org.models_conduct import (
    AttendanceOutcome,  # noqa: F401
    OrgConductSettings,  # noqa: F401
)
from org.models_contributions import (
    ContributionEntry,  # noqa: F401
    ContributionPointValue,  # noqa: F401
)
from org.models_features import OrgFeature  # noqa: F401
from org.models_mmr_requests import MmrChangeRequest  # noqa: F401
from org.models_profiles import (
    PlayerDeadlockProfile,  # noqa: F401
    PlayerDotaProfile,  # noqa: F401
)
from org.models_promotion import (
    PromoSend,  # noqa: F401
    PromoTemplate,  # noqa: F401
)
from org.models_settings import OrgSettings  # noqa: F401


class Organization(models.Model):
    """Organization that owns leagues and tournaments."""

    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="", max_length=10000)
    logo = models.URLField(blank=True, default="")
    discord_link = models.URLField(blank=True, default="")
    discord_server_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Discord server (guild) ID for fetching members",
    )
    rules_template = models.TextField(blank=True, default="", max_length=50000)
    timezone = models.CharField(max_length=50, default="America/New_York")
    members_private = models.BooleanField(
        default=False,
        help_text="Restrict the member list to org staff (hides it from regular members)",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_organizations",
        null=True,
        blank=True,
    )
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="admin_organizations",
        blank=True,
    )
    staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="staff_organizations",
        blank=True,
    )
    promoters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="promoter_organizations",
        blank=True,
    )
    default_league = models.ForeignKey(
        "league.League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_organization",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "app_organization"
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # cacheops' post_save handles invalidation.

    def delete(self, *args: object, **kwargs: object) -> None:
        for league in self.leagues.all():
            invalidate_obj(league)
        super().delete(*args, **kwargs)


class OrgUser(models.Model):
    """User's membership and MMR within an organization."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="org_memberships",
        db_index=True,
    )
    organization = models.ForeignKey(
        "org.Organization",
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


class OrgLog(models.Model):
    """Audit log for organization admin team changes."""

    ACTION_CHOICES = [
        ("add_admin", "Add Admin"),
        ("remove_admin", "Remove Admin"),
        ("add_staff", "Add Staff"),
        ("remove_staff", "Remove Staff"),
        ("add_member", "Add Member"),
        ("transfer_ownership", "Transfer Ownership"),
        ("create", "Create Organization"),
        ("update", "Update Organization"),
        ("delete", "Delete Organization"),
        ("approve_claim", "Approve Profile Claim"),
        ("reject_claim", "Reject Profile Claim"),
        ("set_mmr", "Set MMR"),
        ("enable_feature", "Enable Feature"),
        ("disable_feature", "Disable Feature"),
        ("add_promoter", "Add Promoter"),
        ("remove_promoter", "Remove Promoter"),
        ("set_point_value", "Set Point Value"),
        ("rescore", "Rescore Contributions"),
        ("award_points", "Award Points"),
        ("edit_award", "Edit Award"),
        ("delete_award", "Delete Award"),
        ("complete_event", "Complete Event"),
        ("reopen_event", "Reopen Event"),
        ("set_event_staff", "Set Event Staff"),
        ("delete_user_contributions", "Delete User Contributions"),
        ("set_attendance", "Set Attendance"),
        ("finalize_attendance", "Finalize Attendance"),
        ("void_attendance", "Void Attendance"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="org_actions_performed",
        help_text="User who performed the action",
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_actions_received",
        help_text="User affected by the action (if applicable)",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_orglog"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
        ]
        verbose_name = "Organization Log"
        verbose_name_plural = "Organization Logs"

    def __str__(self) -> str:
        actor_name = self.actor.username if self.actor else "System"
        return f"{actor_name} {self.action} on {self.organization.name}"


class OrgUserGameMmr(models.Model):
    """Org-assigned MMR for one game; a missing row means 0."""

    org_user = models.ForeignKey(
        OrgUser, on_delete=models.CASCADE, related_name="game_mmrs"
    )
    game_type = models.PositiveSmallIntegerField()
    mmr = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

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
