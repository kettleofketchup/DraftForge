from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from org.leadership.constants import (
    MIN_RELEASE_REVIEWS,
    SCORE_MAX,
    SCORE_MIN,
    SETTINGS_DEFAULTS,
    SETTINGS_RANGES,
    VoidKind,
)


def _range(field: str) -> list[MinValueValidator | MaxValueValidator]:
    low, high = SETTINGS_RANGES[field]
    return [MinValueValidator(low), MaxValueValidator(high)]


class OrgLeadershipSettings(models.Model):
    """Per-organization leadership settings. Read via org.leadership.settings."""

    organization = models.OneToOneField(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="leadership_settings",
    )
    review_window_hours = models.PositiveSmallIntegerField(
        default=SETTINGS_DEFAULTS["review_window_hours"],
        validators=_range("review_window_hours"),
    )
    rating_max_points = models.PositiveSmallIntegerField(
        default=SETTINGS_DEFAULTS["rating_max_points"],
        validators=_range("rating_max_points"),
    )
    rating_min_reviewers = models.PositiveSmallIntegerField(
        default=SETTINGS_DEFAULTS["rating_min_reviewers"],
        validators=_range("rating_min_reviewers"),
    )
    ranked_min_reviews = models.PositiveSmallIntegerField(
        default=SETTINGS_DEFAULTS["ranked_min_reviews"],
        validators=_range("ranked_min_reviews"),
    )
    prior_rating = models.FloatField(
        default=SETTINGS_DEFAULTS["prior_rating"], validators=_range("prior_rating")
    )
    prior_strength = models.FloatField(
        default=SETTINGS_DEFAULTS["prior_strength"],
        validators=_range("prior_strength"),
    )
    half_life_days = models.PositiveSmallIntegerField(
        default=SETTINGS_DEFAULTS["half_life_days"],
        validators=_range("half_life_days"),
    )
    max_age_days = models.PositiveSmallIntegerField(
        default=SETTINGS_DEFAULTS["max_age_days"], validators=_range("max_age_days")
    )
    leaderboard_public = models.BooleanField(
        default=SETTINGS_DEFAULTS["leaderboard_public"]
    )
    require_staff_release = models.BooleanField(
        default=SETTINGS_DEFAULTS["require_staff_release"]
    )
    auto_release_after_hours = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=None,
        validators=_range("auto_release_after_hours"),
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

    class Meta:
        verbose_name = "organization leadership settings"
        verbose_name_plural = "organization leadership settings"
        constraints = [
            models.CheckConstraint(
                condition=Q(rating_min_reviewers__gte=MIN_RELEASE_REVIEWS),
                name="leadership_min_reviewers_floor",
            ),
            models.CheckConstraint(
                condition=Q(auto_release_after_hours__isnull=True)
                | Q(
                    auto_release_after_hours__gte=1,
                    auto_release_after_hours__lte=720,
                ),
                name="leadership_auto_release_range",
            ),
        ]

    def __str__(self) -> str:
        return f"Leadership settings for {self.organization_id}"


class CaptainTrait(models.Model):
    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="captain_traits"
    )
    key = models.SlugField(max_length=32)
    label = models.CharField(max_length=48)
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"], name="uniq_captain_trait_key"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.key} @ org {self.organization_id}"


class EventCaptain(models.Model):
    """Captain snapshot taken when an event closes; anchors the review window."""

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="captain_snapshots"
    )
    organization = models.ForeignKey(
        "org.Organization", on_delete=models.CASCADE, related_name="+"
    )
    captain = models.ForeignKey(
        "org.OrgUser", on_delete=models.CASCADE, related_name="captained_events"
    )
    team = models.ForeignKey(
        "app.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    team_name = models.CharField(max_length=255)
    placement = models.PositiveSmallIntegerField(null=True, blank=True)
    teammates = models.ManyToManyField("org.OrgUser", related_name="rater_pools")
    window_closes_at = models.DateTimeField()
    voided_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "captain"], name="uniq_event_captain"
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "window_closes_at"],
                name="leadership_ec_org_window_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"captain {self.captain_id} @ event {self.event_id}"


class CaptainReview(models.Model):
    event_captain = models.ForeignKey(
        EventCaptain, on_delete=models.CASCADE, related_name="reviews"
    )
    rater = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captain_reviews_given",
    )
    submitted_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_kind = models.CharField(
        max_length=16, blank=True, default="", choices=VoidKind.choices
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    void_reason = models.CharField(max_length=500, blank=True, default="")
    moderated_from = models.CharField(
        max_length=16, blank=True, default="", choices=VoidKind.choices
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event_captain", "rater"], name="uniq_captain_review"
            ),
            models.CheckConstraint(
                condition=(Q(voided_at__isnull=True) & Q(void_kind=""))
                | (Q(voided_at__isnull=False) & ~Q(void_kind="")),
                name="captain_review_void_pair",
            ),
        ]
        indexes = [
            models.Index(
                fields=["event_captain", "voided_at"],
                name="leadership_review_ec_void_idx",
            ),
            models.Index(fields=["rater"], name="leadership_review_rater_idx"),
        ]

    def clean(self) -> None:
        if self.event_captain.captain_id == self.rater_id:
            raise ValidationError("A captain cannot review themselves.")

    def __str__(self) -> str:
        return f"review {self.pk} of snapshot {self.event_captain_id}"


class CaptainTraitScore(models.Model):
    review = models.ForeignKey(
        CaptainReview, on_delete=models.CASCADE, related_name="scores"
    )
    trait = models.ForeignKey(
        CaptainTrait, on_delete=models.RESTRICT, related_name="scores"
    )
    score = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["review", "trait"], name="uniq_review_trait"
            ),
            models.CheckConstraint(
                condition=Q(score__gte=SCORE_MIN) & Q(score__lte=SCORE_MAX),
                name="captain_trait_score_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.trait_id}={self.score} on review {self.review_id}"
