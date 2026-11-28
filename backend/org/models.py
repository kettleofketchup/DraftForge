from collections.abc import Iterable
from typing import Any, Self

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from app.cache_utils import invalidate_obj
from common.game import GameType
from org.models_api_connections import (
    OrgApiConnection,  # noqa: F401
    OrgApiMmrDelivery,  # noqa: F401
    OrgApiMmrPullTarget,  # noqa: F401
    OrgApiPromotionAdoption,  # noqa: F401
    OrgApiPromotionBinding,  # noqa: F401
    OrgApiPromotionEventBinding,  # noqa: F401
    OrgApiRunCheckpoint,  # noqa: F401
    OrgApiSyncRun,  # noqa: F401
    OrgMmrRevisionCounter,  # noqa: F401
    OrgMmrSyncState,  # noqa: F401
)
from org.models_api_tokens import (
    OrgApiLimits,  # noqa: F401
    OrgApiToken,  # noqa: F401
    OrgApiTokenUsage,  # noqa: F401
)
from org.models_conduct import (
    AttendanceOutcome,  # noqa: F401
    OrgConductSettings,  # noqa: F401
)
from org.models_contributions import (
    ContributionEntry,  # noqa: F401
    ContributionPointValue,  # noqa: F401
)
from org.models_features import OrgFeature  # noqa: F401
from org.models_leadership import (
    CaptainReview,  # noqa: F401
    CaptainTrait,  # noqa: F401
    CaptainTraitScore,  # noqa: F401
    EventCaptain,  # noqa: F401
    OrgLeadershipSettings,  # noqa: F401
)
from org.models_mmr_requests import MmrChangeRequest  # noqa: F401
from org.models_profiles import (
    PlayerDeadlockProfile,  # noqa: F401
    PlayerDotaProfile,  # noqa: F401
)
from org.models_promotion import (
    PromoSend,  # noqa: F401
    PromoTemplate,  # noqa: F401
)
from org.models_promotion_sync import (
    ExternalPromotionReceipt,  # noqa: F401
    PromotionContactOutbox,  # noqa: F401
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

    @transaction.atomic
    def delete(self, *args: object, **kwargs: object) -> None:
        list(
            self.members.select_for_update().order_by("pk").values_list("pk", flat=True)
        )
        for league in self.leagues.all():
            invalidate_obj(league)
        super().delete(*args, **kwargs)


class OrgUserQuerySet(models.QuerySet["OrgUser"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        with transaction.atomic(using=self.db):
            list(self.select_for_update().order_by("pk").values_list("pk", flat=True))
            return super().delete()


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

    # MMR verification
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    objects: models.Manager["OrgUser"] = models.Manager.from_queryset(OrgUserQuerySet)()
    _membership_user_id: int | None

    @classmethod
    def from_db(
        cls, db: str | None, field_names: Iterable[str], values: Iterable[Any]
    ) -> Self:
        instance = super().from_db(db, field_names, values)
        instance._membership_user_id = instance.__dict__.get("user_id")
        return instance

    def save(self, *args: Any, **kwargs: Any) -> None:
        adding = self._state.adding
        update_fields = kwargs.get("update_fields")
        writes_user = update_fields is None or bool(
            {"user", "user_id"}.intersection(update_fields)
        )
        changed = self.user_id != getattr(self, "_membership_user_id", None)
        if not adding and writes_user and (changed or update_fields is not None):
            # Resolve after org.models finishes loading.
            service = import_string(
                "org.api_connections.identity.member_identity_mutation"
            )
            with service(self):
                super().save(*args, **kwargs)
        else:
            if not adding and update_fields is None:
                deferred = self.get_deferred_fields()
                kwargs["update_fields"] = [
                    field.name
                    for field in self._meta.concrete_fields
                    if not field.primary_key
                    and field.name != "user"
                    and field.attname not in deferred
                ]
                writes_user = False
            super().save(*args, **kwargs)
        if adding or writes_user:
            self._membership_user_id = self.user_id

    def delete(
        self, using: str | None = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        database = using or self._state.db or "default"
        with transaction.atomic(using=database):
            list(
                type(self)
                .objects.using(database)
                .select_for_update()
                .filter(pk=self.pk)
            )
            return super().delete(using=database, keep_parents=keep_parents)

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
        ("void_captain_review", "Void Captain Review"),
        ("unvoid_captain_review", "Unvoid Captain Review"),
        ("release_captain_reviews", "Release Captain Reviews"),
        ("update_leadership_settings", "Update Leadership Settings"),
        ("update_captain_traits", "Update Captain Traits"),
        ("delete_user_leadership", "Delete User Leadership"),
        ("create_api_token", "Create API Token"),
        ("revoke_api_token", "Revoke API Token"),
        ("set_api_limits", "Set API Limits"),
        ("create_api_connection", "Create API Connection"),
        ("edit_api_connection", "Edit API Connection"),
        ("enable_api_connection", "Enable API Connection"),
        ("disable_api_connection", "Disable API Connection"),
        ("archive_api_connection", "Archive API Connection"),
        ("issue_connection_key", "Issue Connection Key"),
        ("rotate_connection_key", "Rotate Connection Key"),
        ("revoke_connection_key", "Revoke Connection Key"),
        ("api_connection_owner_lost", "API Connection Owner Lost"),
        ("resume_mmr_deliveries", "Resume MMR Deliveries"),
        ("resync_mmr_deliveries", "Resync MMR Deliveries"),
        ("edit_promotion_binding", "Edit Promotion Binding"),
        ("adopt_promotion_sync", "Adopt Promotion Sync"),
        ("resume_promotion_outbox", "Resume Promotion Outbox"),
        ("release_promotion_backlog", "Release Promotion Backlog"),
        ("void_promo_point", "Void Promotion Point"),
        ("restore_promo_point", "Restore Promotion Point"),
        ("update_external_contact", "Update External Contact"),
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
