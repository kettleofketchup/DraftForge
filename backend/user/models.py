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
