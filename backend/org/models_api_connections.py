import uuid

from django.conf import settings
from django.core.validators import (
    MaxLengthValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models.deletion import Collector
from django.utils import timezone


def cancel_member_deliveries(
    collector: Collector,
    field: models.ForeignKey,
    sub_objs: models.QuerySet,
    using: str,
) -> None:
    pending = sub_objs.filter(state__in=["pending", "in_flight", "retry", "paused"])
    collector.add_field_update(
        field.model._meta.get_field("state"), "canceled", pending
    )
    collector.add_field_update(
        field.model._meta.get_field("last_reason"), "membership_removed", pending
    )
    collector.add_field_update(field, None, sub_objs)


class OrgApiConnection(models.Model):
    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="api_connections"
    )
    name = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=False)
    inbound_enabled = models.BooleanField(default=False)
    mmr_push_enabled = models.BooleanField(default=False)
    mmr_pull_enabled = models.BooleanField(default=False)
    promotion_push_enabled = models.BooleanField(default=False)
    operations = models.JSONField(default=list, blank=True)
    config_version = models.PositiveBigIntegerField(default=1)
    key_version = models.PositiveBigIntegerField(default=1)
    legacy_backfilled = models.BooleanField(default=False)
    legacy_multi_credential = models.BooleanField(default=False)
    outbound_base_url = models.URLField(max_length=2048, blank=True, default="")
    outbound_auth = models.CharField(max_length=24, default="none")
    outbound_credential_ciphertext = models.TextField(blank=True, default="")
    outbound_credential_key_id = models.CharField(max_length=64, blank=True, default="")
    outbound_credential_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    outbound_authorizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    outbound_credential_set_at = models.DateTimeField(null=True, blank=True)
    mmr_push_config = models.JSONField(default=dict, blank=True)
    mmr_pull_config = models.JSONField(default=dict, blank=True)
    game_type = models.PositiveSmallIntegerField(null=True, blank=True)
    overwrite_policy = models.CharField(
        max_length=24,
        default="missing_only",
        choices=[
            ("missing_only", "Missing only"),
            ("unverified_only", "Unverified only"),
            ("replace", "Replace"),
        ],
    )
    mark_verified = models.BooleanField(default=False)
    interval_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(15), MaxValueValidator(10080)],
    )
    next_due_at = models.DateTimeField(null=True, blank=True)
    last_run_summary = models.JSONField(default=dict, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["mmr_pull_enabled", "next_due_at"], name="org_api_pull_due"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(config_version__gte=1),
                name="org_api_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(interval_minutes__isnull=True)
                | models.Q(interval_minutes__gte=15, interval_minutes__lte=10080),
                name="org_api_interval_bounds",
            ),
        ]


class OrgApiSyncRun(models.Model):
    class Kind(models.TextChoices):
        TEST = "test", "Test"
        MMR_PULL = "mmr_pull", "MMR pull"
        MMR_PUSH = "mmr_push", "MMR push"
        PROMOTION_PUSH = "promotion_push", "Promotion push"

    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        PARTIAL = "partial", "Partial"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("org.Organization", on_delete=models.CASCADE)
    connection = models.ForeignKey(
        OrgApiConnection, on_delete=models.CASCADE, related_name="runs"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    config_version = models.PositiveBigIntegerField(default=1)
    state = models.CharField(max_length=16, choices=State.choices, default=State.QUEUED)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=0)
    row_count = models.PositiveIntegerField(default=0)
    response_bytes = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    skipped_policy_count = models.PositiveIntegerField(default=0)
    missing_identifier_count = models.PositiveIntegerField(default=0)
    verified_count = models.PositiveIntegerField(default=0)
    issue_count = models.PositiveIntegerField(default=0)
    issues = models.JSONField(
        default=list, blank=True, validators=[MaxLengthValidator(100)]
    )
    error_code = models.CharField(max_length=64, blank=True, default="")
    config_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection"],
                condition=models.Q(
                    kind="mmr_pull", state__in=["queued", "running", "partial"]
                ),
                name="org_api_one_active_pull",
            ),
            models.CheckConstraint(
                condition=models.Q(request_count__lte=100),
                name="org_api_run_request_cap",
            ),
            models.CheckConstraint(
                condition=models.Q(row_count__lte=10000), name="org_api_run_row_cap"
            ),
            models.CheckConstraint(
                condition=models.Q(response_bytes__lte=10485760),
                name="org_api_run_byte_cap",
            ),
        ]
        indexes = [
            models.Index(
                fields=["state", "lease_expires_at"], name="org_api_run_lease"
            ),
            models.Index(
                fields=["connection", "-created_at"], name="org_api_run_history"
            ),
        ]


class OrgApiRunCheckpoint(models.Model):
    run = models.OneToOneField(
        OrgApiSyncRun, on_delete=models.CASCADE, related_name="checkpoint"
    )
    phase = models.CharField(max_length=24, default="snapshot")
    page = models.PositiveIntegerField(default=0)
    cursor = models.CharField(max_length=1024, blank=True, default="")
    seen_cursors = models.JSONField(
        default=list, blank=True, validators=[MaxLengthValidator(100)]
    )
    member_snapshot = models.JSONField(
        default=list, blank=True, validators=[MaxLengthValidator(10000)]
    )
    member_offset = models.PositiveIntegerField(default=0)
    commit_offset = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class OrgApiMmrPullTarget(models.Model):
    run = models.ForeignKey(
        OrgApiSyncRun, on_delete=models.CASCADE, related_name="targets"
    )
    org_user = models.ForeignKey(
        "org.OrgUser", on_delete=models.CASCADE, related_name="mmr_pull_targets"
    )
    game_type = models.PositiveSmallIntegerField()
    source_page = models.PositiveIntegerField(default=0)
    source_index = models.PositiveIntegerField(default=0)
    identifier_snapshot = models.JSONField(default=dict, blank=True)
    expected_revision = models.PositiveBigIntegerField(default=0)
    proposed_value = models.IntegerField()
    outcome_code = models.CharField(max_length=64, blank=True, default="")
    applied_revision = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "org_user", "game_type"],
                name="org_api_pull_target_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["run", "outcome_code", "id"], name="org_api_target_progress"
            )
        ]


class OrgMmrRevisionCounter(models.Model):
    organization = models.ForeignKey("org.Organization", on_delete=models.CASCADE)
    game_type = models.PositiveSmallIntegerField()
    revision = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "game_type"], name="org_mmr_counter_unique"
            )
        ]


class OrgMmrSyncState(models.Model):
    org_user = models.ForeignKey(
        "org.OrgUser", on_delete=models.CASCADE, related_name="mmr_sync_states"
    )
    game_type = models.PositiveSmallIntegerField()
    revision = models.PositiveBigIntegerField(default=0)
    value = models.IntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_source_connection = models.ForeignKey(
        OrgApiConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_user", "game_type"], name="org_mmr_sync_state_unique"
            )
        ]


class OrgApiMmrDelivery(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_FLIGHT = "in_flight", "In flight"
        RETRY = "retry", "Retry"
        PAUSED = "paused", "Paused"
        APPLIED = "applied", "Applied"
        SUPERSEDED = "superseded", "Superseded"
        CANCELED = "canceled", "Canceled"

    connection = models.ForeignKey(
        OrgApiConnection, on_delete=models.CASCADE, related_name="mmr_deliveries"
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=cancel_member_deliveries,
        null=True,
        blank=True,
        related_name="mmr_deliveries",
    )
    game_type = models.PositiveSmallIntegerField()
    revision = models.PositiveBigIntegerField()
    payload = models.JSONField(default=dict)
    origin_connection = models.ForeignKey(
        OrgApiConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    delivery_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    config_version = models.PositiveBigIntegerField(default=1)
    destination_origin = models.CharField(max_length=2048, blank=True, default="")
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    due_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_reason = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "org_user", "game_type", "revision"],
                name="org_api_mmr_delivery_unique",
            )
        ]
        indexes = [
            models.Index(fields=["state", "due_at"], name="org_api_mmr_due"),
            models.Index(
                fields=["state", "lease_expires_at"], name="org_api_mmr_lease"
            ),
        ]


class OrgApiPromotionBinding(models.Model):
    organization = models.OneToOneField(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="api_promotion_binding",
    )
    connection = models.OneToOneField(
        OrgApiConnection, on_delete=models.CASCADE, related_name="promotion_binding"
    )
    guild_id = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)


class OrgApiPromotionEventBinding(models.Model):
    binding = models.ForeignKey(
        OrgApiPromotionBinding, on_delete=models.CASCADE, related_name="events"
    )
    event = models.OneToOneField(
        "events.Event", on_delete=models.CASCADE, related_name="api_promotion_binding"
    )
    occasion_id = models.PositiveBigIntegerField()
    effective_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["binding", "occasion_id"],
                name="org_api_promotion_occasion_unique",
            )
        ]


class OrgApiPromotionAdoption(models.Model):
    organization = models.OneToOneField(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="api_promotion_adoption",
    )
    connection = models.OneToOneField(
        OrgApiConnection, on_delete=models.CASCADE, related_name="promotion_adoption"
    )
    adopted_at = models.DateTimeField(default=timezone.now)
    adopted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
