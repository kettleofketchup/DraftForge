import nh3
from django.core.exceptions import ValidationError
from django.db import models

from app.models import TOURNAMNET_TYPE_CHOICES, DraftStyles, GameType

GAME_TYPE_TEAM_SIZE = {
    GameType.DOTA2: 5,
    GameType.DEADLOCK: 6,
}


class EventState(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    SIGNUPS_OPEN = "signups_open", "Signups Open"
    ROLL_CALL = "roll_call", "Roll Call"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


EVENT_STATE_TRANSITIONS = {
    EventState.UPCOMING: [EventState.SIGNUPS_OPEN, EventState.CANCELLED],
    EventState.SIGNUPS_OPEN: [
        EventState.ROLL_CALL,
        EventState.IN_PROGRESS,
        EventState.CANCELLED,
    ],
    EventState.ROLL_CALL: [EventState.IN_PROGRESS, EventState.CANCELLED],
    EventState.IN_PROGRESS: [EventState.COMPLETED],
    EventState.COMPLETED: [],
    EventState.CANCELLED: [],
}


class SignupStatus(models.TextChoices):
    RSVP = "rsvp", "RSVP"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    CONFIRMED = "confirmed", "Confirmed"
    WAITLISTED = "waitlisted", "Waitlisted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class SignupType(models.TextChoices):
    USER = "user", "User"
    TEAM = "team", "Team"


class RepeatFrequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    EVERY_TWO_WEEKS = "every_two_weeks", "Every Two Weeks"
    MONTHLY = "monthly", "Monthly"


class RollCallMode(models.TextChoices):
    MANUAL = "manual", "Manual"


class TournamentTemplateMixin(models.Model):
    """Abstract mixin for tournament creation blueprint fields."""

    tournament_name = models.CharField(max_length=255)
    tournament_league = models.ForeignKey(
        "app.League",
        on_delete=models.CASCADE,
        related_name="+",
    )
    tournament_type = models.CharField(
        max_length=30,
        choices=TOURNAMNET_TYPE_CHOICES,
        default="double_elimination",
    )
    game_type = models.IntegerField(choices=GameType.choices, default=GameType.DOTA2)
    draft_type = models.CharField(
        max_length=10,
        choices=[(s.value, s.value.title()) for s in DraftStyles],
        default=DraftStyles.shuffle.value,
    )
    people_per_team = models.IntegerField(default=5)
    number_of_teams = models.IntegerField(null=True, blank=True, default=2)
    tournament_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class EventConfigMixin(models.Model):
    """Abstract mixin for event configuration fields."""

    timezone = models.CharField(max_length=50, default="America/New_York")
    min_players = models.IntegerField(null=True, blank=True)
    max_players = models.IntegerField(null=True, blank=True)
    signup_deadline_hours = models.IntegerField(null=True, blank=True)
    allow_team_signups = models.BooleanField(default=False)
    allow_user_signups = models.BooleanField(default=True)
    auto_approve = models.BooleanField(default=False)
    auto_confirm = models.BooleanField(default=False)
    require_mmr_verified = models.BooleanField(default=False)
    require_steam_id = models.BooleanField(default=False)
    require_profile_complete = models.BooleanField(default=False)
    roll_call_enabled = models.BooleanField(default=False)
    roll_call_mode = models.CharField(
        max_length=20,
        choices=RollCallMode.choices,
        default=RollCallMode.MANUAL,
    )
    auto_start = models.BooleanField(default=True)

    def clean(self):
        if self.roll_call_enabled and self.auto_start:
            raise ValidationError(
                "auto_start must be False when roll_call_enabled is True."
            )

    class Meta:
        abstract = True


class EventRepeater(TournamentTemplateMixin, EventConfigMixin):
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="event_repeaters",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    frequency = models.CharField(max_length=20, choices=RepeatFrequency.choices)
    day_of_week = models.IntegerField(null=True, blank=True)
    time_of_day = models.TimeField()
    starts_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)
    generate_days_ahead = models.IntegerField(default=7)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_event_repeaters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.frequency})"

    def save(self, *args, **kwargs):
        if self.description:
            self.description = nh3.clean(self.description)
        super().save(*args, **kwargs)


class Event(TournamentTemplateMixin, EventConfigMixin):
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_repeater = models.ForeignKey(
        EventRepeater,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    scheduled_at = models.DateTimeField()
    signups_open_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(
        max_length=20, choices=EventState.choices, default=EventState.UPCOMING
    )
    tournament = models.ForeignKey(
        "app.Tournament",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_event",
    )
    created_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event_repeater", "scheduled_at"],
                name="unique_repeater_scheduled_at",
                condition=models.Q(event_repeater__isnull=False),
            ),
        ]
        indexes = [models.Index(fields=["state", "scheduled_at"])]

    def __str__(self):
        return f"{self.name} ({self.scheduled_at:%Y-%m-%d})"

    def save(self, *args, **kwargs):
        if self.description:
            self.description = nh3.clean(self.description)
        super().save(*args, **kwargs)

    def transition_state(self, new_state):
        allowed = EVENT_STATE_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Cannot transition from '{self.state}' to '{new_state}'. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        self.state = new_state
        self.save(update_fields=["state", "updated_at"])


class EventTeam(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=255)
    captain = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="captained_event_teams",
    )
    members = models.ManyToManyField(
        "app.CustomUser", blank=True, related_name="event_teams"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.name} ({self.event.name})"


class EventSignup(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="signups")
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="event_signups",
    )
    event_team = models.ForeignKey(
        EventTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signups",
    )
    signup_type = models.CharField(
        max_length=10, choices=SignupType.choices, default=SignupType.USER
    )
    status = models.CharField(
        max_length=20, choices=SignupStatus.choices, default=SignupStatus.RSVP
    )
    waitlist_position = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"], name="unique_event_user_signup"
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.event.name} ({self.status})"
