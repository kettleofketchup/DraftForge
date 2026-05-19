from cacheops import invalidate_obj
from django.db import models


class BaseUserProfile(models.Model):
    """User-global, single-value profile data.

    Owns fields that are true for the user regardless of game or org —
    nickname, avatar, future display-only fields. Game-specific data
    lives on DotaUserProfile / DeadlockUserProfile (T2); org-scoped
    data lives on OrgUserProfile (T3).
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
        invalidate_obj(self.user)
