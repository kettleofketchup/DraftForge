from django.db import models

from app.cache_utils import invalidate_obj
from league.models_rating import (
    LeagueMatch,  # noqa: F401
    LeagueMatchParticipant,  # noqa: F401
    LeagueRating,  # noqa: F401
)


class League(models.Model):
    """League belonging to a single organization."""

    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="leagues",
        null=True,
        blank=True,
    )
    steam_league_id = models.IntegerField(unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="", max_length=10000)
    rules = models.TextField(blank=True, default="", max_length=50000)
    prize_pool = models.CharField(max_length=100, blank=True, default="")
    timezone = models.CharField(max_length=50, default="America/New_York")
    admins = models.ManyToManyField(
        "app.CustomUser",
        related_name="admin_leagues",
        blank=True,
    )
    staff = models.ManyToManyField(
        "app.CustomUser",
        related_name="staff_leagues",
        blank=True,
    )
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Rating system configuration
    RATING_SYSTEM_CHOICES = [
        ("elo", "Elo"),
        ("fixed_delta", "Fixed Delta"),
    ]
    rating_system = models.CharField(
        max_length=20,
        choices=RATING_SYSTEM_CHOICES,
        default="elo",
        help_text="Rating calculation method",
    )
    k_factor_default = models.FloatField(
        default=32.0,
        help_text="Default K-factor for Elo calculations",
    )
    k_factor_placement = models.FloatField(
        default=64.0,
        help_text="K-factor for players in placement games",
    )
    placement_games = models.PositiveIntegerField(
        default=10,
        help_text="Number of placement games before using default K-factor",
    )
    fixed_delta = models.FloatField(
        default=25.0,
        help_text="Fixed rating change per game (for fixed_delta system)",
    )

    # Age decay configuration
    age_decay_enabled = models.BooleanField(
        default=False,
        help_text="Enable age-based decay for older matches",
    )
    age_decay_half_life_days = models.PositiveIntegerField(
        default=180,
        help_text="Half-life in days for age decay calculation",
    )
    age_decay_minimum = models.FloatField(
        default=0.1,
        help_text="Minimum decay factor (0.0-1.0)",
    )

    # Recalculation constraints
    recalc_max_age_days = models.PositiveIntegerField(
        default=90,
        help_text="Maximum age in days for match recalculation",
    )
    recalc_mmr_threshold = models.PositiveIntegerField(
        default=500,
        help_text="Maximum MMR change allowed for recalculation",
    )

    class Meta:
        db_table = "app_league"
        ordering = ["name"]
        verbose_name = "League"
        verbose_name_plural = "Leagues"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.steam_league_id})"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation handled by cacheops post_save signal; explicit
        # cascade to organization stays so the org's cached child list
        # refreshes when this league mutates.
        if self.organization:
            invalidate_obj(self.organization)

    def delete(self, *args: object, **kwargs: object) -> None:
        if self.organization:
            invalidate_obj(self.organization)
        super().delete(*args, **kwargs)


class LeagueUser(models.Model):
    """User's membership in a league with MMR snapshot from their org membership."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True,
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True,
    )
    league = models.ForeignKey(
        "league.League",
        on_delete=models.CASCADE,
        related_name="members",
    )
    mmr = models.IntegerField(default=0, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "league"]

    def __str__(self) -> str:
        return f"{self.user.username} in {self.league.name}"


class LeagueLog(models.Model):
    """Audit log for league admin team changes."""

    ACTION_CHOICES = [
        ("add_admin", "Add Admin"),
        ("remove_admin", "Remove Admin"),
        ("add_staff", "Add Staff"),
        ("remove_staff", "Remove Staff"),
        ("add_member", "Add Member"),
        ("link_organization", "Link Organization"),
        ("unlink_organization", "Unlink Organization"),
        ("create", "Create League"),
        ("update", "Update League"),
        ("delete", "Delete League"),
    ]

    league = models.ForeignKey(
        "league.League",
        on_delete=models.CASCADE,
        related_name="logs",
    )
    actor = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="league_actions_performed",
        help_text="User who performed the action",
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="league_actions_received",
        help_text="User affected by the action (if applicable)",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_leaguelog"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["league", "-created_at"]),
        ]
        verbose_name = "League Log"
        verbose_name_plural = "League Logs"

    def __str__(self) -> str:
        actor_name = self.actor.username if self.actor else "System"
        return f"{actor_name} {self.action} on {self.league.name}"
