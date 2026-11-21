from typing import Self

from django.conf import settings
from django.core.validators import (
    MaxLengthValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Q

from org.conduct.constants import (
    COUNTED,
    DEFAULT_BACK_OF_LINE_BELOW,
    DEFAULT_BLOCK_BELOW,
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_LATE_CANCEL_HOURS,
    DEFAULT_LATE_CANCEL_WEIGHT,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MIN_EVENTS,
    DEFAULT_PRIOR_SHOW_RATE,
    DEFAULT_PRIOR_STRENGTH,
    DEFAULT_REQUIRE_APPROVAL_BELOW,
    REASON_MAX_LENGTH,
    SETTINGS_RANGES,
    Outcome,
    OutcomeSource,
)


def _range(field: str) -> list[MinValueValidator | MaxValueValidator]:
    low, high = SETTINGS_RANGES[field]
    return [MinValueValidator(low), MaxValueValidator(high)]


class OrgConductSettings(models.Model):
    """Per-organization conduct settings. Read via org.conduct.gate.get_conduct_settings."""

    organization = models.OneToOneField(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="conduct_settings",
    )
    late_cancel_hours = models.PositiveSmallIntegerField(
        default=DEFAULT_LATE_CANCEL_HOURS, validators=_range("late_cancel_hours")
    )
    late_cancel_weight = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=DEFAULT_LATE_CANCEL_WEIGHT,
        validators=_range("late_cancel_weight"),
    )
    half_life_days = models.PositiveSmallIntegerField(
        default=DEFAULT_HALF_LIFE_DAYS, validators=_range("half_life_days")
    )
    max_age_days = models.PositiveSmallIntegerField(
        default=DEFAULT_MAX_AGE_DAYS, validators=_range("max_age_days")
    )
    prior_show_rate = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=DEFAULT_PRIOR_SHOW_RATE,
        validators=_range("prior_show_rate"),
    )
    prior_strength = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=DEFAULT_PRIOR_STRENGTH,
        validators=_range("prior_strength"),
    )
    min_events = models.PositiveSmallIntegerField(
        default=DEFAULT_MIN_EVENTS, validators=_range("min_events")
    )
    leaderboard_public = models.BooleanField(default=True)
    back_of_line_enabled = models.BooleanField(default=False)
    back_of_line_below = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=DEFAULT_BACK_OF_LINE_BELOW,
        validators=_range("back_of_line_below"),
    )
    require_approval_enabled = models.BooleanField(default=False)
    require_approval_below = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=DEFAULT_REQUIRE_APPROVAL_BELOW,
        validators=_range("require_approval_below"),
    )
    block_enabled = models.BooleanField(default=False)
    block_below = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=DEFAULT_BLOCK_BELOW,
        validators=_range("block_below"),
    )
    enforce_on_new_members = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "organization conduct settings"
        verbose_name_plural = "organization conduct settings"

    def __str__(self) -> str:
        return f"Conduct settings for {self.organization_id}"


class AttendanceOutcomeQuerySet(models.QuerySet["AttendanceOutcome"]):
    def counted(self) -> Self:
        return self.filter(
            finalized_at__isnull=False,
            voided_at__isnull=True,
            committed=True,
            outcome__in=COUNTED,
        )

    def for_event(self, event_id: int) -> Self:
        return self.filter(event_id=event_id)


class AttendanceOutcome(models.Model):
    """One attendance outcome per event per member."""

    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="attendance_outcomes",
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="attendance_outcomes",
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_outcomes",
    )
    event_name = models.CharField(max_length=255)
    event_starts_at = models.DateTimeField()
    signup = models.ForeignKey(
        "events.EventSignup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    outcome = models.CharField(
        max_length=16, choices=Outcome.choices, default=Outcome.PENDING
    )
    source = models.CharField(
        max_length=16, choices=OutcomeSource.choices, default=OutcomeSource.DEFAULT
    )
    committed = models.BooleanField(default=True)
    signup_status_at_close = models.CharField(max_length=24, blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reason = models.TextField(
        blank=True, default="", validators=[MaxLengthValidator(REASON_MAX_LENGTH)]
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AttendanceOutcomeQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "org_user"],
                condition=Q(event__isnull=False),
                name="uniq_attendance_per_event_member",
            ),
            models.CheckConstraint(
                condition=~Q(source=OutcomeSource.STAFF) | ~Q(reason=""),
                name="attendance_staff_reason_required",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "event_starts_at"],
                name="conduct_outcome_org_start_idx",
            ),
            models.Index(
                fields=["org_user", "event_starts_at"],
                name="conduct_outcome_mbr_start_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outcome} for org_user {self.org_user_id} @ {self.event_name}"
