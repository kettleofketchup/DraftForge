from django.db import models

from org.settings_constants import StaffOverridePolicy, default_warning_codes


class OrgSettings(models.Model):
    """Per-organization settings. Read via org.settings_service.get_org_settings."""

    StaffOverridePolicy = StaffOverridePolicy

    organization = models.OneToOneField(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="settings",
    )
    staff_override_policy = models.CharField(
        max_length=16,
        choices=StaffOverridePolicy.choices,
        default=StaffOverridePolicy.SILENT,
    )
    staff_override_warning_codes = models.JSONField(
        default=default_warning_codes, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "organization settings"
        verbose_name_plural = "organization settings"

    def __str__(self) -> str:
        return f"Settings for {self.organization_id}"
