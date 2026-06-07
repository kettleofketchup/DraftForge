from django.db import models


class BaseUserProfile(models.Model):
    """User-global, single-value profile data.

    Owns fields that are true for the user regardless of game or org —
    nickname, avatar, future display-only fields. Game-specific data
    lives on DotaUserProfile / DeadlockUserProfile (T2); org-scoped
    data lives on OrgUserProfile (T3).

    Cacheops invalidation: BaseUserProfile is registered in CACHEOPS with
    ops="all", so post_save fires automatically. Every @cached_as site
    that ships nickname/avatar lists BaseUserProfile as a dependency
    (T1.9), so its post_save eviction cascades through those caches.
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

    def __str__(self):
        return f"BaseUserProfile({self.user.username or self.user_id})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-create user-wide game profiles. Idempotent via get_or_create.
        # invalidate_after_commit (not bare invalidate_obj) because this runs
        # inside the parent CustomUser.save() transaction (epic lesson:
        # auto-create within transaction.atomic).
        from app.cache_utils import invalidate_after_commit

        # CRITICAL: positions default MUST be a callable so PositionsModel is
        # created ONLY on the create branch. A bare
        # defaults={"positions": PositionsModel.objects.create()} evaluates the
        # create() on EVERY call (the dict is built before the lookup), leaking
        # an orphan PositionsModel row on every idempotent resave. Django
        # resolves callable defaults only when actually creating.
        from app.models import PositionsModel

        dota, dota_created = DotaUserProfile.objects.get_or_create(
            base_profile=self,
            defaults={"positions": lambda: PositionsModel.objects.create()},
        )
        deadlock, dl_created = DeadlockUserProfile.objects.get_or_create(base_profile=self)
        targets = []
        if dota_created:
            targets.append(dota)
        if dl_created:
            targets.append(deadlock)
        if targets:
            invalidate_after_commit(*targets)


class DotaUserProfile(models.Model):
    """User-wide Dota profile. Owns position preferences + MMR-verification state
    that used to live on CustomUser (T2 epic)."""

    base_profile = models.OneToOneField(
        BaseUserProfile,
        on_delete=models.CASCADE,
        related_name="dota_user_profile",
        db_index=True,
    )
    # NO related_name on positions: PositionsModel.save() walks the Django
    # default reverse accessor `dotauserprofile_set`. Changing this silently
    # breaks cache invalidation (T2 hard constraint).
    positions = models.ForeignKey(
        "app.PositionsModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Dota User Profile"

    def __str__(self):
        return f"DotaUserProfile({self.base_profile.user_id})"


class DeadlockUserProfile(models.Model):
    """User-wide Deadlock profile. Mirrors org.PlayerDeadlockProfile's
    user-relevant fields (T2 epic)."""

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

    def __str__(self):
        return f"DeadlockUserProfile({self.base_profile.user_id})"
