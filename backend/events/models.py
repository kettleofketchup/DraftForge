import copy
from collections.abc import Mapping, Sequence

import nh3
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone as tz

from app.cache_utils import invalidate_after_commit
from app.models import (
    TOURNAMNET_TYPE_CHOICES,
    DotaLobbyLaunch,
    DotaLobbyMode,
    DraftStyles,
    GameMode,
    GameType,
    TimeoutAction,
)
from events.ready_check_constants import (
    READY_CHECK_FIELD_RANGES,
    PostCullFillMode,
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckLowCompletionAction,
    ReadyCheckOutcome,
    ReadyCheckPhase,
    ReadyCheckScope,
)
from lobby import passwords as lobby_passwords

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
    MANUAL = "manual", "Staff-verified"
    AUTOMATIC = "automatic", "Automatic"


def _range_validators(field: str) -> list[MinValueValidator | MaxValueValidator]:
    low, high = READY_CHECK_FIELD_RANGES[field]
    return [MinValueValidator(low), MaxValueValidator(high)]


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
    draft_timer_enabled = models.BooleanField(default=True)
    draft_grace_time_ms = models.IntegerField(default=30000)
    draft_reserve_time_ms = models.IntegerField(default=30000)
    draft_timeout_action = models.CharField(
        max_length=32,
        choices=TimeoutAction.choices,
        default=TimeoutAction.SKIP_TURN,
    )
    hero_timer_enabled = models.BooleanField(default=True)
    hero_grace_time_ms = models.IntegerField(default=30000)
    hero_reserve_time_ms = models.IntegerField(default=90000)

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
    ready_check_scope = models.CharField(
        max_length=20,
        choices=ReadyCheckScope.choices,
        default=ReadyCheckScope.MAIN_ONLY,
        help_text="Which signups the ready check asks to confirm",
    )
    ready_check_open_minutes = models.PositiveIntegerField(
        default=120,
        validators=_range_validators("ready_check_open_minutes"),
        help_text="Minutes before start that the ready check opens",
    )
    ready_check_escalation_minutes = models.PositiveIntegerField(
        default=30,
        validators=_range_validators("ready_check_escalation_minutes"),
        help_text="Minutes before start to nudge unconfirmed members (0 = off)",
    )
    ready_check_close_minutes = models.PositiveIntegerField(
        default=10,
        validators=_range_validators("ready_check_close_minutes"),
        help_text="Minutes before start that the ready check closes",
    )
    ready_check_chase_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=30,
        validators=_range_validators("ready_check_chase_minutes"),
        help_text="Minutes before close to alert staff about each unconfirmed member (blank = off)",
    )
    ready_check_min_completion_pct = models.PositiveSmallIntegerField(
        default=70,
        validators=_range_validators("ready_check_min_completion_pct"),
        help_text="Minimum percentage confirmed for the check to be binding",
    )
    ready_check_low_completion_action = models.CharField(
        max_length=20,
        choices=ReadyCheckLowCompletionAction.choices,
        default=ReadyCheckLowCompletionAction.NON_BINDING,
        help_text="What happens when completion is below the minimum",
    )
    ready_check_notify_on_signup = models.BooleanField(
        default=True,
        help_text="Tell members at signup that a ready check will run",
    )
    ready_check_drop_notice = models.BooleanField(
        default=True,
        help_text="Notify members who are dropped by the ready check",
    )
    start_cull_enabled = models.BooleanField(
        default=False,
        help_text="Drop members who are not present shortly after start",
    )
    start_cull_minutes_after = models.PositiveIntegerField(
        default=1,
        validators=_range_validators("start_cull_minutes_after"),
        help_text="Minutes after start to run the start cull",
    )
    post_cull_fill_mode = models.CharField(
        max_length=20,
        choices=PostCullFillMode.choices,
        default=PostCullFillMode.LINE_ORDER,
        help_text="How freed seats are filled after drops",
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
    event_voice_channel_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        validators=[discord_id_validator],
        help_text="Discord voice channel ID for the event call",
    )
    voice_presence_confirms = models.BooleanField(
        default=False,
        help_text="Joining the event voice channel confirms the ready check",
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


class DotaLobbyConfigMixin(models.Model):
    """dota_lobby settings a series hands to its events and their tournaments.

    Same choices and defaults as the Tournament fields they are copied to.
    The password itself is a concrete field on EventRepeater and Event, not
    part of this mixin, so the auto-built copy lists never copy it blindly
    (events.services.series_lobby_password decides).
    """

    dota_lobby_mode = models.CharField(
        max_length=8, choices=DotaLobbyMode.choices, default=DotaLobbyMode.OFF
    )
    dota_lobby_launch = models.CharField(
        max_length=8, choices=DotaLobbyLaunch.choices, default=DotaLobbyLaunch.MANUAL
    )
    dota_lobby_region = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="dota_lobby region name; empty uses DOTA_LOBBY_REGION",
    )
    discord_send_lobby_info = models.BooleanField(
        default=False,
        help_text="DM rostered players the lobby name and password",
    )
    dota_lobby_password_mode = models.CharField(
        max_length=8,
        choices=lobby_passwords.PasswordMode.choices,
        default=lobby_passwords.PasswordMode.RANDOM,
        help_text="fixed: staff set the lobby password; random: generated per event",
    )

    class Meta:
        abstract = True


class EventRepeater(
    TournamentTemplateMixin,
    EventConfigMixin,
    DiscordEventConfigMixin,
    DiscordTournamentConfigMixin,
    DotaLobbyConfigMixin,
):
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="event_repeaters",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    frequency = models.CharField(max_length=20, choices=RepeatFrequency.choices)
    day_of_week = models.IntegerField(null=True, blank=True)  # 0=Sunday, 6=Saturday
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
    # The fixed lobby password (fixed mode only; empty in random mode, where
    # each event generates its own). Never in public serializers.
    dota_lobby_password = models.CharField(
        max_length=lobby_passwords.MAX_LENGTH, blank=True, default=""
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
    DotaLobbyConfigMixin,
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
    ends_at = models.DateTimeField(null=True, blank=True)
    signups_open_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(
        max_length=20, choices=EventState.choices, default=EventState.UPCOMING
    )
    host = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_events",
    )
    helpers = models.ManyToManyField(
        "app.CustomUser", blank=True, related_name="helped_events"
    )
    contributions_awarded_at = models.DateTimeField(null=True, blank=True)
    is_off_schedule = models.BooleanField(
        default=False,
        help_text=(
            "Attached to a series but not generated by its schedule; excluded "
            "from realign and from the series config cascade."
        ),
    )
    tournament = models.ForeignKey(
        "app.Tournament",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_event",
    )
    # The event's effective lobby password: the series' fixed one, one typed
    # for this event, or a generated one. Copied onto the event's tournament;
    # every lobby of the event uses it. Shown only to staff and registered
    # players (events.lobby_password), never in public serializers.
    dota_lobby_password = models.CharField(
        max_length=lobby_passwords.MAX_LENGTH, blank=True, default=""
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

    def clean(self) -> None:
        super().clean()
        if (
            self.ends_at is not None
            and self.scheduled_at is not None
            and self.ends_at <= self.scheduled_at
        ):
            raise ValidationError({"ends_at": "End time must be after the start time."})

    def save(self, *args, **kwargs):
        if self.description:
            self.description = nh3.clean(self.description)
        if (
            self.dota_lobby_password_mode == lobby_passwords.PasswordMode.RANDOM
            and not self.dota_lobby_password
        ):
            self.dota_lobby_password = lobby_passwords.generate_password()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "dota_lobby_password"}
        super().save(*args, **kwargs)

    def transition_state(
        self,
        new_state: str,
        *,
        transitions: Mapping[str, Sequence[str]] = EVENT_STATE_TRANSITIONS,
    ) -> None:
        allowed = transitions.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Cannot transition from '{self.state}' to '{new_state}'. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        now = tz.now()
        changed = (
            Event.objects.nocache()
            .filter(pk=self.pk, state=self.state)
            .update(state=new_state, updated_at=now)
        )
        if not changed:
            current = (
                Event.objects.nocache()
                .filter(pk=self.pk)
                .values_list("state", flat=True)
                .first()
            )
            raise ValueError(
                f"Cannot transition from '{self.state}' to '{new_state}': "
                f"the event is now '{current}'."
            )
        stale = copy.copy(self)
        self.state = new_state
        self.updated_at = now
        invalidate_after_commit(stale, self)


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


class ReadyCheck(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="ready_checks"
    )
    phase = models.CharField(
        max_length=20,
        choices=ReadyCheckPhase.choices,
        default=ReadyCheckPhase.OPEN,
    )
    outcome = models.CharField(
        max_length=20, choices=ReadyCheckOutcome.choices, blank=True, default=""
    )
    settings_snapshot = models.JSONField(default=dict, blank=True)
    completion_pct = models.PositiveSmallIntegerField(null=True, blank=True)
    opened_at = models.DateTimeField(default=tz.now)
    escalated_at = models.DateTimeField(null=True, blank=True)
    chased_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    last_progress_at = models.DateTimeField(default=tz.now)
    opened_by = models.ForeignKey(
        "app.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    resolved_by = models.ForeignKey(
        "app.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    resolve_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event"],
                condition=~models.Q(phase=ReadyCheckPhase.CANCELLED),
                name="events_readycheck_one_live_per_event",
            ),
        ]
        indexes = [
            models.Index(fields=["phase"], name="events_readycheck_phase_idx"),
        ]

    def __str__(self) -> str:
        return f"Ready check {self.pk} ({self.event_id}, {self.phase})"


class ReadyCheckEntry(models.Model):
    ready_check = models.ForeignKey(
        ReadyCheck, on_delete=models.CASCADE, related_name="entries"
    )
    signup = models.ForeignKey(
        EventSignup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ready_check_entries",
    )
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="ready_check_entries",
    )
    state = models.CharField(
        max_length=20,
        choices=ReadyCheckEntryState.choices,
        default=ReadyCheckEntryState.PENDING,
    )
    confirmed_via = models.CharField(
        max_length=20, choices=ReadyCheckConfirmVia.choices, blank=True, default=""
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    nudged_at = models.DateTimeField(null=True, blank=True)
    dropped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ready_check", "signup"],
                name="events_rcentry_unique_signup",
            ),
            models.UniqueConstraint(
                fields=["ready_check", "user"], name="events_rcentry_unique_user"
            ),
        ]
        indexes = [
            models.Index(
                fields=["ready_check", "state"], name="events_rcentry_state_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in ready check {self.ready_check_id} ({self.state})"

    @classmethod
    def for_signup(
        cls, ready_check: ReadyCheck, signup: EventSignup
    ) -> "ReadyCheckEntry":
        return cls(ready_check=ready_check, signup=signup, user_id=signup.user_id)

    def clean(self) -> None:
        super().clean()
        if self.signup_id is None:
            return
        if self.signup.user_id != self.user_id:
            raise ValidationError({"user": "Must match the signup's user."})
        if self.signup.event_id != self.ready_check.event_id:
            raise ValidationError({"signup": "Must belong to the ready check's event."})


class EventVoicePresence(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="voice_presences"
    )
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="event_voice_presences",
    )
    guild_id = models.CharField(
        max_length=20, blank=True, default="", validators=[discord_id_validator]
    )
    channel_id = models.CharField(
        max_length=20, blank=True, default="", validators=[discord_id_validator]
    )
    present = models.BooleanField(default=False)
    first_joined_at = models.DateTimeField(null=True, blank=True)
    last_joined_at = models.DateTimeField(null=True, blank=True)
    last_left_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"], name="events_voicepresence_unique"
            ),
        ]
        indexes = [
            models.Index(
                fields=["event", "present"], name="events_voicepres_present_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} voice presence for event {self.event_id}"
