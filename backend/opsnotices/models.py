from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from opsnotices.registry import NoticeCategory, NoticeSeverity

OPEN_STATES: tuple[str, ...] = ("open",)

CATEGORY_CHOICES: list[tuple[str, str]] = [(c.value, c.value) for c in NoticeCategory]
SEVERITY_CHOICES: list[tuple[str, str]] = [(s.value, s.value) for s in NoticeSeverity]


class OpsNotice(models.Model):
    class State(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    class DeliveryState(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        UNROUTED = "unrouted", "Unrouted"

    organization = models.ForeignKey(
        "app.Organization", on_delete=models.CASCADE, related_name="ops_notices"
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ops_notices",
    )
    event_key = models.PositiveBigIntegerField(default=0)
    event_name = models.CharField(max_length=255, blank=True, default="")
    event_repeater_id = models.PositiveBigIntegerField(null=True, blank=True)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    key = models.CharField(max_length=100, db_index=True)
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES)
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(max_length=24, choices=State.choices, default=State.OPEN)
    occurrences = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_note = models.CharField(max_length=200, blank=True, default="")
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    delivery_state = models.CharField(
        max_length=16, choices=DeliveryState.choices, default=DeliveryState.PENDING
    )
    last_emit_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_seen_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key", "event_key", "dedupe_key"],
                condition=Q(closed_at__isnull=True) & ~Q(dedupe_key=""),
                name="opsnotice_open_dedupe_uniq",
            ),
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "key",
                    "event_key",
                    "dedupe_key",
                    "last_emit_id",
                ],
                condition=Q(last_emit_id__isnull=False),
                name="opsnotice_emit_id_uniq",
            ),
            models.CheckConstraint(
                condition=Q(occurrences__gte=1), name="opsnotice_occurrences_gte_1"
            ),
            models.CheckConstraint(
                condition=Q(state__in=OPEN_STATES, closed_at__isnull=True)
                | (~Q(state__in=OPEN_STATES) & Q(closed_at__isnull=False)),
                name="opsnotice_state_closed_at_consistent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "state", "-last_seen_at"],
                name="opsnotice_org_state_seen_idx",
            ),
            models.Index(fields=["event", "state"], name="opsnotice_event_state_idx"),
            models.Index(fields=["closed_at"], name="opsnotice_closed_at_idx"),
            models.Index(
                fields=["category", "last_seen_at"], name="opsnotice_category_seen_idx"
            ),
            models.Index(
                fields=["delivery_state", "last_seen_at"],
                name="opsnotice_delivery_seen_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.key} ({self.state})"
