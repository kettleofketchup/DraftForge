from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils.module_loading import import_string

from app.cache_utils import invalidate_after_commit

if TYPE_CHECKING:
    from app.models import CustomUser


@contextmanager
def track_user_identity(user: CustomUser, kwargs: dict[str, Any]) -> Iterator[None]:
    fields = {"steam_account_id", "steamid", "discordId"}
    update_fields = kwargs.get("update_fields")
    snapshot = getattr(user, "_identity_snapshot", {})
    changed = (
        update_fields is not None and bool(fields.intersection(update_fields))
    ) or any(
        name in user.__dict__ and user.__dict__[name] != snapshot.get(name)
        for name in fields
    )
    if (
        user._state.adding
        or not apps.is_installed("org")
        or not changed
        or (update_fields is not None and not fields.intersection(update_fields))
    ):
        yield
        return
    # Resolve after model loading: light workers do not install org.
    service = import_string("org.api_connections.identity.user_identity_mutation")
    with service(user):
        yield


class PositionsModel(models.Model):
    carry = models.IntegerField(
        default=0,
        help_text="Rank of the carry position from 0 (No play) to 5 (best)",
    )
    mid = models.IntegerField(
        default=0, help_text="Rank of the mid position from 0 (No play) to 5 (best)"
    )
    offlane = models.IntegerField(
        default=0,
        help_text="Rank of the offlane position from 0 (No play) to 5 (best)",
    )
    soft_support = models.IntegerField(
        default=0,
        help_text="Rank of the soft support position from 0 (No play) to 5 (best)",
    )
    hard_support = models.IntegerField(
        default=0,
        help_text="Rank of the hard support position from 0 (No play) to 5 (best)",
    )

    class Meta:
        db_table = "app_positionsmodel"

    def __str__(self) -> str:
        return f"Carry: {self.carry}, Mid: {self.mid}, Offlane: {self.offlane}, Soft Support: {self.soft_support}, Hard Support: {self.hard_support}"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Invalidate linked DotaUserProfiles and their parents. .nocache():
        # a cached join (invalidated only on DotaUserProfile) could miss a
        # freshly linked profile. Org positions are pos_1..5 booleans on
        # org.PlayerDotaProfile, which cacheops invalidates on its own.
        dota_profiles = list(
            self.dotauserprofile_set.select_related("base_profile__user").nocache()
        )
        targets = []
        for dp in dota_profiles:
            targets += [dp, dp.base_profile, dp.base_profile.user]
        if targets:
            invalidate_after_commit(*targets)


class BaseUserProfile(models.Model):
    """User-global, single-value profile data.

    Owns fields that are true for the user regardless of game or org —
    nickname, avatar, future display-only fields. Game-specific data
    lives on DotaUserProfile / DeadlockUserProfile; org-scoped
    data lives on OrgUser and its game profiles.

    Cacheops invalidation: BaseUserProfile is registered in CACHEOPS with
    ops="all", so post_save fires automatically. Every @cached_as site
    that ships nickname/avatar lists BaseUserProfile as a dependency
    (enforced by user/tests/test_cacheops.py), so its post_save eviction
    cascades through those caches.
    No explicit invalidate_obj() call needed — main's cacheops audit
    (commit 02ff547d) removed the same pattern from 9 other models.
    """

    user = models.OneToOneField(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="base_profile",
        db_index=True,
    )
    nickname = models.TextField(null=True, blank=True)
    avatar = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Base User Profile"

    def __str__(self) -> str:
        return f"BaseUserProfile({self.user.username or self.user_id})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        # Auto-create user-wide game profiles. Idempotent via get_or_create.
        # invalidate_after_commit (not bare invalidate_obj) because this runs
        # inside the parent CustomUser.save() transaction.
        # CRITICAL: positions default MUST be a callable so PositionsModel is
        # created ONLY on the create branch. A bare
        # defaults={"positions": PositionsModel.objects.create()} evaluates the
        # create() on EVERY call (the dict is built before the lookup), leaking
        # an orphan PositionsModel row on every idempotent resave. Django
        # resolves callable defaults only when actually creating.
        dota, dota_created = DotaUserProfile.objects.get_or_create(
            base_profile=self,
            defaults={"positions": lambda: PositionsModel.objects.create()},
        )
        deadlock, dl_created = DeadlockUserProfile.objects.get_or_create(
            base_profile=self
        )
        targets = []
        if dota_created:
            targets.append(dota)
        if dl_created:
            targets.append(deadlock)
        if targets:
            invalidate_after_commit(*targets)


class DotaUserProfile(models.Model):
    """User-wide Dota profile. Owns position preferences + MMR-verification state
    that used to live on CustomUser."""

    base_profile = models.OneToOneField(
        BaseUserProfile,
        on_delete=models.CASCADE,
        related_name="dota_user_profile",
        db_index=True,
    )
    # NO related_name on positions: PositionsModel.save() walks the Django
    # default reverse accessor `dotauserprofile_set`. Changing this silently
    # breaks cache invalidation.
    positions = models.ForeignKey(
        PositionsModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Dota User Profile"

    def __str__(self) -> str:
        return f"DotaUserProfile({self.base_profile.user_id})"


class DeadlockUserProfile(models.Model):
    """User-wide Deadlock profile. Mirrors org.PlayerDeadlockProfile's
    user-relevant fields."""

    base_profile = models.OneToOneField(
        BaseUserProfile,
        on_delete=models.CASCADE,
        related_name="deadlock_user_profile",
        db_index=True,
    )
    rank = models.CharField(max_length=64, null=True, blank=True)
    rank_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Deadlock User Profile"

    def __str__(self) -> str:
        return f"DeadlockUserProfile({self.base_profile.user_id})"


class ProfileClaimRequest(models.Model):
    """
    Request to claim a profile (merge a Steam-only profile into a Discord account).

    Flow:
    1. User with Discord ID sees profile with Steam ID but no Discord
    2. User clicks "Claim" which creates a pending request
    3. Org admin reviews and approves/rejects
    4. If approved, the merge happens and target profile is deleted
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    claimer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="claim_requests_made",
        help_text="User requesting to claim the profile (has Discord ID)",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="claim_requests_received",
        help_text="Profile being claimed (has Steam ID, no Discord). NULL after merge.",
    )
    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="claim_requests",
        help_text="Organization where the target profile is a member",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claim_requests_reviewed",
        help_text="Admin who approved/rejected the request",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if rejected)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "app_profileclaimrequest"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "status", "-created_at"],
                name="app_profile_organiz_4b1a91_idx",
            ),
            models.Index(
                fields=["claimer", "status"], name="app_profile_claimer_2ce297_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["claimer", "target_user"],
                condition=models.Q(status="pending"),
                name="unique_pending_claim_request",
            )
        ]

    def __str__(self) -> str:
        target = self.target_user
        label = (target.nickname or target.steamid) if target else "(deleted profile)"
        return f"{self.claimer.username} -> {label} ({self.status})"
