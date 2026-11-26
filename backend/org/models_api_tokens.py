from django.conf import settings
from django.db import models

from org.api_tokens.operations import default_operations

DEFAULT_PER_MINUTE = 60
DEFAULT_PER_DAY = 5000


class OrgApiToken(models.Model):
    """App token that lets one user call the org API as themselves."""

    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="api_tokens"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_api_tokens",
    )
    name = models.CharField(max_length=64)
    prefix = models.CharField(max_length=16, unique=True)
    secret_hash = models.CharField(max_length=64)
    operations = models.JSONField(
        default=default_operations,
        help_text="Granted operations, sorted (see org.api_tokens.operations)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "user"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}) @ org {self.organization_id}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def grants(self, operation: str) -> bool:
        return isinstance(self.operations, list) and str(operation) in self.operations


class OrgApiTokenUsage(models.Model):
    """Daily request counters for one token."""

    token = models.ForeignKey(
        OrgApiToken, on_delete=models.CASCADE, related_name="usage"
    )
    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    date = models.DateField()
    request_count = models.PositiveIntegerField(default=0)
    throttled_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["token", "date"], name="uniq_org_api_token_usage_day"
            ),
        ]
        indexes = [models.Index(fields=["organization", "date"])]

    def __str__(self) -> str:
        return f"token {self.token_id} {self.date}: {self.request_count}"


class OrgApiLimits(models.Model):
    """Per-org override of the per-token request limits."""

    organization = models.OneToOneField(
        "org.Organization", on_delete=models.CASCADE, related_name="api_limits"
    )
    per_minute = models.PositiveIntegerField(default=DEFAULT_PER_MINUTE)
    per_day = models.PositiveIntegerField(default=DEFAULT_PER_DAY)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name_plural = "Org API limits"

    def __str__(self) -> str:
        return f"org {self.organization_id}: {self.per_minute}/min {self.per_day}/day"
