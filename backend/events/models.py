import copy
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, NoReturn

import nh3
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, router, transaction
from django.db.models import F
from django.db.models.expressions import DatabaseDefault
from django.db.models.functions import Now
from django.utils import timezone as tz

from app.cache_utils import invalidate_after_commit
from app.models import (
    TOURNAMNET_TYPE_CHOICES,
    DotaLobbyLaunch,
    DotaLobbyMode,
    DraftStyles,
    GameMode,
    GameType,
)
from draft.models import TimeoutAction
from events import line
from events.constants import (  # noqa: F401 — re-exported for backward compat
    EVENT_STATE_TRANSITIONS,
    LINE_EXCLUDED_STATUSES,
    ActorRole,
    Commitment,
    EventState,
    RepeatFrequency,
    RsvpClass,
    SignupAction,
    SignupMeans,
    SignupOpenMode,
    SignupStatus,
    SignupType,
    StartMentionScope,
)
from events.exceptions import ImmutableFieldError, LedgerAppendOnlyError
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
from telemetry.logging import get_logger

log = get_logger(__name__)

discord_id_validator = RegexValidator(
    r"^(\d{17,20})?$",
    "Must be a valid Discord snowflake ID",
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
    # Inert until #504.
    signup_deadline_hours = models.IntegerField(null=True, blank=True)
    # Inert until #547.
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
    signup_open_mode = models.CharField(
        max_length=16,
        choices=SignupOpenMode.choices,
        default=SignupOpenMode.MANUAL,
        help_text=(
            "How signups open. Manual: staff open them. Immediately: opens "
            "signups for every upcoming event already generated in the series "
            "horizon. Hours before start: opens signups_open_hours_before the "
            "event starts."
        ),
    )
    signups_open_hours_before = models.PositiveIntegerField(
        default=72,
        help_text="Hours before the start that signups open (scheduled mode)",
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
    discord_start_mention = models.BooleanField(
        default=False,
        help_text="Mention signed-up members on the signup post before the event starts",
    )
    discord_start_mention_minutes = models.IntegerField(
        default=15,
        validators=[MinValueValidator(1)],
        help_text="Minutes before event to mention signed-up members",
    )
    discord_start_mention_scope = models.CharField(
        max_length=16,
        choices=StartMentionScope.choices,
        default=StartMentionScope.ALL_ACTIVE,
        help_text="Which signed-up members to mention",
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

    def __str__(self) -> str:
        return f"{self.name} ({self.frequency})"

    def save(self, *args: Any, **kwargs: Any) -> None:
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
    conduct_finalized_at = models.DateTimeField(null=True, blank=True)
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

    def __str__(self) -> str:
        return f"{self.name} ({self.scheduled_at:%Y-%m-%d})"

    def clean(self) -> None:
        super().clean()
        if (
            self.ends_at is not None
            and self.scheduled_at is not None
            and self.ends_at <= self.scheduled_at
        ):
            raise ValidationError({"ends_at": "End time must be after the start time."})

    def save(self, *args: Any, **kwargs: Any) -> None:
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
        self.refresh_signup_post_on_commit()

    def refresh_signup_post_on_commit(self) -> None:
        """Re-render the Discord signup post once the state change commits."""
        # Function-local: events.discord imports events.models.
        from events.discord.dispatch import notify_signup_changed

        transaction.on_commit(lambda: notify_signup_changed(self))


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

    def __str__(self) -> str:
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
    # events.eligibility.ReasonCode codes from the last requirements check.
    unmet_requirements = models.JSONField(default=list, blank=True)
    # Reason.as_dict() for each code in unmet_requirements.
    eligibility_reasons = models.JSONField(
        default=list,
        blank=True,
        db_default=models.Value([], output_field=models.JSONField()),
    )
    eligibility_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signed_up_at = models.DateTimeField(db_default=Now())
    line_seq = models.PositiveIntegerField(null=True, blank=True)
    commitment = models.CharField(
        max_length=8, choices=Commitment.choices, db_default=Commitment.MAIN
    )
    rsvp_class = models.CharField(
        max_length=16,
        choices=RsvpClass.choices,
        default=RsvpClass.STANDARD,
        db_default=RsvpClass.STANDARD,
    )
    first_signed_up_at = models.DateTimeField(null=True, db_default=Now())
    first_commitment = models.CharField(
        max_length=8, choices=Commitment.choices, null=True, db_default=Commitment.MAIN
    )
    first_rsvp_class = models.CharField(
        max_length=16,
        choices=RsvpClass.choices,
        null=True,
        db_default=RsvpClass.STANDARD,
    )

    objects = line.EventSignupQuerySet.as_manager()

    class Meta:
        ordering = [F("line_seq").asc(nulls_last=True), "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"], name="unique_event_user_signup"
            ),
        ]
        indexes = [
            models.Index(
                fields=["event", "line_seq"], name="eventsignup_event_line_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.event.name} ({self.status})"

    _line_loaded: dict[str, Any]
    _TRACKED: tuple[str, ...] = ("event_id", "line_seq", *line.FIRST_FIELDS)
    _EXISTING_FIELDS: tuple[str, ...] = (
        "event_id",
        "line_seq",
        "signed_up_at",
        "commitment",
        "rsvp_class",
        *line.FIRST_FIELDS,
    )

    @classmethod
    def from_db(
        cls, db: str | None, field_names: Sequence[str], values: Sequence[Any]
    ) -> "EventSignup":
        instance = super().from_db(db, field_names, values)
        instance._capture_line_state()
        return instance

    def refresh_from_db(
        self,
        using: str | None = None,
        fields: Iterable[str] | None = None,
        from_queryset: models.QuerySet | None = None,
    ) -> None:
        fields = list(fields) if fields is not None else None
        super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        if fields is None or not hasattr(self, "_line_loaded"):
            self._capture_line_state()
        else:
            self._capture_line_state(
                {"event_id" if f == "event" else f for f in fields}
            )

    def _capture_line_state(self, only: set[str] | None = None) -> None:
        deferred = self.get_deferred_fields()
        state = {} if only is None else dict(self._line_loaded)
        for attname in self._TRACKED:
            if only is not None and attname not in only:
                continue
            if attname in deferred:
                state.pop(attname, None)
            else:
                state[attname] = getattr(self, attname)
        self._line_loaded = state

    def save(self, *args: Any, **kwargs: Any) -> None:
        existing: dict[str, Any] | None = None
        if (
            self._state.adding
            and self.pk is not None
            and not kwargs.get("force_insert")
        ):
            existing = (
                type(self)
                ._base_manager.nocache()
                .filter(pk=self.pk)
                .values(*self._EXISTING_FIELDS)
                .first()
            )
        restamped = False
        if self._state.adding and existing is None:
            self._save_insert(*args, **kwargs)
        else:
            restamped = self._save_update(existing, *args, **kwargs)
        written = _written_attnames(kwargs.get("update_fields"))
        if written is None or not hasattr(self, "_line_loaded"):
            self._capture_line_state()
        else:
            self._capture_line_state(written | ({"line_seq"} if restamped else set()))

    def _save_insert(self, *args: Any, **kwargs: Any) -> None:
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            if _unset(self.line_seq):
                at = None if _unset(self.signed_up_at) else self.signed_up_at
                for name, value in line.stamp(self.event, at=at).items():
                    setattr(self, name, value)
            elif _unset(self.signed_up_at):
                self.signed_up_at = tz.now()
            if _unset(self.commitment):
                self.commitment = (
                    Commitment.MAYBE
                    if self.status == SignupStatus.TENTATIVE
                    else Commitment.MAIN
                )
            never_signed_up = self.status in LINE_EXCLUDED_STATUSES
            for first in line.FIRST_FIELDS:
                if _unset(getattr(self, first)):
                    setattr(
                        self,
                        first,
                        None if never_signed_up else line.first_value(self, first),
                    )
            super().save(*args, **kwargs)

    def _save_update(
        self, existing: dict[str, Any] | None, *args: Any, **kwargs: Any
    ) -> bool:
        if existing is not None:
            for name, value in existing.items():
                if _unset(getattr(self, name)):
                    setattr(self, name, value)
            loaded = existing
        else:
            loaded = getattr(self, "_line_loaded", {})
        self._guard_first_fields(loaded)
        self._fill_first_fields(kwargs)
        written = _written_attnames(kwargs.get("update_fields"))
        if (written is None or "event_id" in written) and self._event_changed(loaded):
            using = kwargs.get("using") or router.db_for_write(
                type(self), instance=self
            )
            with transaction.atomic(using=using):
                from_event_id = loaded["event_id"]
                for name, value in line.stamp(self.event).items():
                    setattr(self, name, value)
                update_fields = kwargs.get("update_fields")
                if update_fields is not None:
                    kwargs["update_fields"] = [
                        *update_fields,
                        *(
                            f
                            for f in ("line_seq", "signed_up_at")
                            if f not in update_fields
                        ),
                    ]
                super().save(*args, **kwargs)
            log.info(
                "signup_line_restamped_on_event_change",
                system="events",
                subsystem="line",
                signup_id=self.pk,
                from_event_id=from_event_id,
                event_id=self.event_id,
                line_seq=self.line_seq,
            )
            return True
        super().save(*args, **kwargs)
        return False

    def _fill_first_fields(self, kwargs: dict[str, Any]) -> None:
        if self.status in LINE_EXCLUDED_STATUSES:
            return
        if "first_signed_up_at" in self.get_deferred_fields():
            return
        if self.first_signed_up_at is not None:
            return
        for first in line.FIRST_FIELDS:
            setattr(self, first, line.first_value(self, first, at=tz.now()))
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = [
                *update_fields,
                *(f for f in line.FIRST_FIELDS if f not in update_fields),
            ]

    def _guard_first_fields(self, loaded: Mapping[str, Any]) -> None:
        deferred = self.get_deferred_fields()
        checked = [f for f in line.FIRST_FIELDS if f not in deferred]
        originals = dict(loaded)
        missing = [f for f in checked if f not in originals]
        if missing and self.pk is not None:
            originals.update(
                type(self)
                ._base_manager.nocache()
                .filter(pk=self.pk)
                .values(*missing)
                .first()
                or {}
            )
        changed = [
            f
            for f in checked
            if f in originals
            and originals[f] is not None
            and getattr(self, f) != originals[f]
        ]
        if changed:
            log.warning(
                "signup_first_fields_mutation_blocked",
                system="events",
                subsystem="line",
                signup_id=self.pk,
                fields=changed,
            )
            raise ImmutableFieldError(f"EventSignup fields are immutable: {changed}")

    def _event_changed(self, loaded: Mapping[str, Any]) -> bool:
        if "event_id" not in loaded or "event_id" in self.get_deferred_fields():
            return False
        if self.event_id == loaded["event_id"]:
            return False
        return "line_seq" not in loaded or self.line_seq == loaded["line_seq"]


def _written_attnames(update_fields: Iterable[str] | None) -> set[str] | None:
    if update_fields is None:
        return None
    return {"event_id" if f == "event" else f for f in update_fields}


def _unset(value: object) -> bool:
    return value is None or isinstance(value, DatabaseDefault)


LEDGER_MUTABLE_FIELDS = frozenset(
    {"subject_user", "subject_user_id", "actor_user", "actor_user_id"}
)


def _ledger_blocked(
    entry_id: int | None, operation: str, fields: list[str]
) -> NoReturn:
    log.warning(
        "signup_ledger_mutation_blocked",
        system="events",
        subsystem="ledger",
        entry_id=entry_id,
        operation=operation,
        fields=fields,
    )
    raise LedgerAppendOnlyError(
        f"SignupLedgerEntry is append-only: {operation} {fields}"
    )


class SignupLedgerEntryQuerySet(models.QuerySet):
    def delete(self) -> tuple[int, dict[str, int]]:
        _ledger_blocked(None, "queryset_delete", [])

    def update(self, **kwargs: Any) -> int:
        if not kwargs or not set(kwargs) <= LEDGER_MUTABLE_FIELDS:
            _ledger_blocked(None, "queryset_update", sorted(kwargs))
        return super().update(**kwargs)

    def purge(self) -> int:
        count, _ = models.QuerySet.delete(self)
        log.info(
            "signup_ledger_purged", system="events", subsystem="ledger", count=count
        )
        return count


class SignupLedgerEntry(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="ledger_entries",
    )
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        related_name="+",
    )
    signup = models.ForeignKey(
        EventSignup,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        related_name="ledger_entries",
    )
    event_snapshot = models.JSONField()
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="signup_ledger_entries",
    )
    subject_snapshot = models.JSONField()
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signup_ledger_actions",
    )
    actor_snapshot = models.JSONField(null=True)
    actor_role = models.CharField(max_length=16, choices=ActorRole.choices)
    means = models.CharField(max_length=32, choices=SignupMeans.choices)
    on_behalf = models.BooleanField(default=False)
    action = models.CharField(max_length=32, choices=SignupAction.choices)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    reason = models.TextField(blank=True, default="")
    rules_overridden = models.JSONField(default=list)
    caused_by = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        related_name="effects",
    )
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    occurred_at = models.DateTimeField(default=tz.now)

    objects = SignupLedgerEntryQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "pk"]
        indexes = [
            models.Index(
                fields=["event", "occurred_at"], name="ledger_event_occurred_idx"
            ),
            models.Index(
                fields=["subject_user", "occurred_at"],
                name="ledger_subject_occurred_idx",
            ),
            models.Index(
                fields=["event", "subject_user", "action"],
                name="ledger_event_subject_act_idx",
            ),
            models.Index(
                fields=["organization", "occurred_at"], name="ledger_org_occurred_idx"
            ),
            models.Index(fields=["correlation_id"], name="ledger_correlation_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} event={self.event_id} user={self.subject_user_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            names = None if update_fields is None else list(update_fields)
            if not names or not set(names) <= LEDGER_MUTABLE_FIELDS:
                _ledger_blocked(self.pk, "save", names or [])
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        _ledger_blocked(self.pk, "delete", [])


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

    def __str__(self) -> str:
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

    def __str__(self) -> str:
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
        if self.signup_id is None or self.ready_check_id is None:
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
