from django.db import models

from app.cache_utils import invalidate_obj
from app.models import CustomUser, Tournament


class HeroDraftState(models.TextChoices):
    """State machine states for Captain's Mode hero draft."""

    WAITING_FOR_CAPTAINS = "waiting_for_captains", "Waiting for Captains"
    ROLLING = "rolling", "Rolling"
    CHOOSING = "choosing", "Choosing"
    DRAFTING = "drafting", "Drafting"
    PAUSED = "paused", "Paused"
    RESUMING = "resuming", "Resuming"  # 3-second countdown before resuming
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class HeroDraft(models.Model):
    """Captain's Mode hero draft for a tournament game."""

    game = models.OneToOneField(
        "app.Game", on_delete=models.CASCADE, related_name="herodraft"
    )
    state = models.CharField(
        max_length=32,
        choices=HeroDraftState.choices,
        default=HeroDraftState.WAITING_FOR_CAPTAINS,
    )
    roll_winner = models.ForeignKey(
        "DraftTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_rolls",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    resuming_until = models.DateTimeField(null=True, blank=True)
    is_manual_pause = models.BooleanField(
        default=False
    )  # True if paused manually by captain/staff
    timer_enabled = models.BooleanField(default=True)
    grace_time_ms = models.IntegerField(default=30000)

    class Meta:
        db_table = "app_herodraft"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation handled by cacheops post_save signal.

    def __str__(self) -> str:
        return f"HeroDraft for {self.game}"

    def snapshot_timer_options(self, tournament: "Tournament | None") -> int:
        """Copy the tournament's hero timer options onto this draft (unsaved).

        Returns the reserve time each DraftTeam should start with.
        """
        if tournament is None:
            self.timer_enabled = True
            self.grace_time_ms = HeroDraft._meta.get_field("grace_time_ms").default
            return DraftTeam._meta.get_field("reserve_time_remaining").default
        options = tournament.get_draft_options(fresh=True)
        self.timer_enabled = options.hero_timer_enabled
        self.grace_time_ms = options.hero_grace_time_ms
        return options.hero_reserve_time_ms


class DraftTeam(models.Model):
    """One of the two teams in a hero draft."""

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="draft_teams"
    )
    tournament_team = models.ForeignKey(
        "app.Team", on_delete=models.CASCADE, related_name="hero_draft_teams"
    )
    is_first_pick = models.BooleanField(null=True, blank=True)
    is_radiant = models.BooleanField(null=True, blank=True)
    reserve_time_remaining = models.IntegerField(default=90000)  # 90 seconds in ms
    is_ready = models.BooleanField(default=False)
    is_connected = models.BooleanField(default=False)

    class Meta:
        db_table = "app_draftteam"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation via cacheops post_save. Cascade to draft so
        # the draft's cached team list refreshes when any team mutates.
        if self.draft_id:
            invalidate_obj(self.draft)

    @property
    def captain(self) -> CustomUser | None:
        return self.tournament_team.captain

    def __str__(self) -> str:
        return f"DraftTeam: {self.tournament_team} in {self.draft}"


class HeroDraftRound(models.Model):
    """A single pick or ban action in the draft."""

    ACTION_CHOICES = [
        ("ban", "Ban"),
        ("pick", "Pick"),
    ]

    STATE_CHOICES = [
        ("planned", "Planned"),
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="rounds"
    )
    draft_team = models.ForeignKey(
        DraftTeam, on_delete=models.CASCADE, related_name="rounds"
    )
    round_number = models.IntegerField()
    action_type = models.CharField(max_length=8, choices=ACTION_CHOICES)
    hero_id = models.IntegerField(null=True, blank=True)
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default="planned")
    grace_time_ms = models.IntegerField(default=30000)  # 30 seconds
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "app_herodraftround"
        ordering = ["round_number"]

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation via cacheops post_save. Cascade to draft so
        # the draft's cached round list refreshes on each pick/ban.
        if self.draft_id:
            invalidate_obj(self.draft)

    def __str__(self) -> str:
        return f"Round {self.round_number}: {self.action_type} by {self.draft_team}"


class HeroDraftEvent(models.Model):
    """Audit log for hero draft events."""

    EVENT_CHOICES = [
        ("captain_connected", "Captain Connected"),
        ("captain_disconnected", "Captain Disconnected"),
        ("captain_ready", "Captain Ready"),
        ("draft_paused", "Draft Paused"),
        ("draft_resumed", "Draft Resumed"),
        ("roll_triggered", "Roll Triggered"),
        ("roll_result", "Roll Result"),
        ("choice_made", "Choice Made"),
        ("round_started", "Round Started"),
        ("hero_selected", "Hero Selected"),
        ("round_timeout", "Round Timeout"),
        ("draft_completed", "Draft Completed"),
    ]

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    draft_team = models.ForeignKey(
        DraftTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_herodraftevent"
        ordering = ["created_at"]

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation via cacheops post_save. Cascade to draft so
        # the draft's event log refreshes when a new event is recorded.
        if self.draft_id:
            invalidate_obj(self.draft)

    def __str__(self) -> str:
        return f"{self.event_type} at {self.created_at}"
