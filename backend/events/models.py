import nh3
from django.core.validators import RegexValidator
from django.db import models

from app.models import TOURNAMNET_TYPE_CHOICES, DraftStyles, GameMode, GameType

discord_id_validator = RegexValidator(
    r"^(\d{17,20})?$",
    "Must be a valid Discord snowflake ID",
)


from events.constants import (  # noqa: F401 — re-exported for backward compat
    EVENT_STATE_TRANSITIONS,
    EventState,
    RepeatFrequency,
    SignupStatus,
    SignupType,
)


class RollCallMode(models.TextChoices):
    MANUAL = "manual", "Manual"


class TournamentTemplateMixin(models.Model):
    """Abstract mixin for tournament creation blueprint fields."""

    tournament_name = models.CharField(max_length=255, blank=True, default="")
    tournament_league = models.ForeignKey(
        "app.League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
    game_mode = models.CharField(
        max_length=20, choices=GameMode.choices, default=GameMode.NORMAL
    )
    custom_game_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom game/lobby name (for custom game mode)",
    )
    captains_draft_time = models.IntegerField(
        default=10,
        help_text="Seconds per draft pick in Captain's Mode",
    )
    lobby_steam_league_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Steam league ID for Dota 2 lobby ticket",
    )
    auto_create_hero_drafts = models.BooleanField(default=False)

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
    # Approval Requirements — which rank types are allowed
    allow_active_mmr = models.BooleanField(
        default=True,
        help_text="Allow players with active MMR to sign up",
    )
    allow_previous_rank = models.BooleanField(
        default=True,
        help_text="Allow players with previous (expired) rank to sign up",
    )
    allow_battlecup_rating = models.BooleanField(
        default=True,
        help_text="Allow never-ranked players (battle cup tier) to sign up",
    )

    class Meta:
        abstract = True


class DiscordEventConfigMixin(models.Model):
    """Abstract mixin for Discord integration configuration."""

    discord_create_event = models.BooleanField(
        default=False, help_text="Create a Discord scheduled event"
    )
    discord_sync_signups = models.BooleanField(
        default=False, help_text="Sync signups to the Discord event"
    )
    discord_event_title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom title for Discord event (blank = use event name)",
    )
    discord_event_description = models.TextField(
        blank=True, default="", help_text="Custom description for Discord event"
    )
    discord_event_info = models.TextField(
        blank=True,
        default="",
        help_text="Additional info shown in the Discord event",
    )
    discord_signup_reminder = models.BooleanField(
        default=True,
        help_text="DM subscribers who haven't signed up before the event",
    )
    discord_signup_reminder_hours = models.IntegerField(
        default=24, help_text="Hours before event to send signup reminder"
    )
    discord_confirm_attendance = models.BooleanField(
        default=False,
        help_text="Require attendance confirmation via Discord message reply on event day",
    )
    discord_confirm_attendance_hours = models.IntegerField(
        default=2,
        help_text="Hours before event to send attendance confirmation request",
    )
    discord_profile_reminder = models.BooleanField(
        default=False,
        help_text="Remind users to complete their profile before the event",
    )
    discord_profile_reminder_hours = models.IntegerField(
        default=24,
        help_text="Hours before event to send profile update reminder",
    )
    discord_mark_interested = models.BooleanField(
        default=False,
        help_text="Mark signups as 'interested' on the Discord scheduled event",
    )
    discord_post_signups = models.BooleanField(
        default=False,
        help_text="Post an event embed to a channel for reaction-based signups",
    )
    discord_post_signups_channel_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[discord_id_validator],
        help_text="Discord channel ID to post signup embed in",
    )
    discord_announcement = models.BooleanField(
        default=False,
        help_text="Post a pre-day announcement in a channel",
    )
    discord_announcement_channel_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[discord_id_validator],
        help_text="Discord channel ID for pre-day announcement",
    )
    discord_announcement_hours = models.IntegerField(
        default=24,
        help_text="Hours before event to post announcement",
    )
    discord_announcement_role_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Discord role IDs to @ mention in the announcement",
    )
    discord_signup_role_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Discord role IDs to @ mention in the signup post",
    )
    discord_subscriber_dm = models.BooleanField(
        default=False,
        help_text="Send DM to subscribers before event starts",
    )
    discord_subscriber_dm_hours = models.IntegerField(
        default=24,
        help_text="Hours before event to send subscriber DM",
    )
    discord_require_rank_screenshot = models.BooleanField(
        default=False,
        help_text="Require active ranked players to upload MMR screenshot",
    )
    discord_require_battlecup_screenshot = models.BooleanField(
        default=False,
        help_text="Require never-ranked players to upload battle cup ticket screenshot",
    )
    min_mmr = models.IntegerField(
        null=True,
        blank=True,
        help_text="Minimum MMR required for event approval (null = no minimum)",
    )

    class Meta:
        abstract = True


class DiscordTournamentConfigMixin(models.Model):
    """Discord notification options for tournaments created from events."""

    discord_send_draft_link = models.BooleanField(
        default=True,
        help_text="DM participants the draft link when the team draft starts",
    )
    discord_send_herodraft_link = models.BooleanField(
        default=True,
        help_text="DM participants the hero draft link when a hero draft starts",
    )

    class Meta:
        abstract = True


class EventRepeater(
    TournamentTemplateMixin,
    EventConfigMixin,
    DiscordEventConfigMixin,
    DiscordTournamentConfigMixin,
):
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
    discord_notify_new_events = models.BooleanField(
        default=True,
        help_text="Notify users when new events are generated and ready for signup",
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


class Event(
    TournamentTemplateMixin,
    EventConfigMixin,
    DiscordEventConfigMixin,
    DiscordTournamentConfigMixin,
):
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


class RepeaterSubscription(models.Model):
    """User subscription to an event repeater for new event notifications."""

    event_repeater = models.ForeignKey(
        EventRepeater,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="repeater_subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event_repeater", "user"],
                name="unique_repeater_user_subscription",
            ),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} → {self.event_repeater.name}"


class OrgEventDefaults(
    TournamentTemplateMixin,
    EventConfigMixin,
    DiscordEventConfigMixin,
    DiscordTournamentConfigMixin,
):
    """Organization-level default configuration for new events and repeaters.

    All fields are optional with sensible defaults. When creating a new event
    or repeater, the frontend pre-fills the form from these defaults.
    """

    organization = models.OneToOneField(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="event_defaults",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Org event defaults"

    def __str__(self):
        return f"Event defaults for {self.organization.name}"
