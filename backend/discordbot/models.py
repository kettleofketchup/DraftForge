from django.conf import settings
from django.db import models


class EventTemplate(models.Model):
    """Reusable template for Discord events and announcements."""

    TEMPLATE_TYPE_CHOICES = [
        ("event", "Discord Event"),
        ("announcement", "Announcement"),
    ]

    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPE_CHOICES)
    title = models.CharField(max_length=256)
    description = models.TextField()
    color = models.CharField(max_length=7)  # Hex color
    channel_id = models.CharField(max_length=20)
    include_rsvp = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.template_type})"


class ScheduledEvent(models.Model):
    """Recurring or one-time scheduled event posts."""

    template = models.ForeignKey(
        EventTemplate,
        on_delete=models.CASCADE,
        related_name="scheduled_events",
    )

    # Scheduling
    is_recurring = models.BooleanField(default=False)
    day_of_week = models.IntegerField(null=True, blank=True)  # 0=Sunday, 6=Saturday
    time_of_day = models.TimeField(null=True, blank=True)
    next_post_at = models.DateTimeField()

    # Discord references (after posting)
    discord_event_id = models.CharField(max_length=20, null=True, blank=True)
    discord_message_id = models.CharField(max_length=20, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.template.name} - next: {self.next_post_at}"


class RSVP(models.Model):
    """Tracks user RSVP responses via reactions."""

    STATUS_CHOICES = [
        ("yes", "Attending"),
        ("maybe", "Maybe"),
        ("no", "Not Attending"),
    ]

    scheduled_event = models.ForeignKey(
        ScheduledEvent,
        on_delete=models.CASCADE,
        related_name="rsvps",
    )
    discord_user_id = models.CharField(max_length=20)
    discord_username = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    responded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["scheduled_event", "discord_user_id"]

    def __str__(self):
        return f"{self.discord_username}: {self.status}"


class DiscordMessageLog(models.Model):
    """Audit log for all outbound Discord messages.

    Lease semantics (PR-1):
        success = NULL  → lease held; send in flight
        success = True  → message sent successfully
        success = False → send attempted and failed (transient or permanent)

    The partial unique index on (source, source_id) WHERE success IS NOT FALSE
    serializes claim attempts: only one worker can hold a NULL or True row for
    a given (source, source_id) at a time. Failed (False) rows are reclaimable
    so transient Discord errors don't permanently brick reminders. The
    sweep_stale_discord_leases beat task ages out NULL >5min and False >1hr.
    """

    # What was sent
    channel_id = models.CharField(max_length=64)
    embed_data = models.JSONField()

    # Discord response
    discord_message_id = models.CharField(max_length=64, null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)
    success = models.BooleanField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Context — what triggered this message
    source = models.CharField(max_length=64, default="unknown")
    source_id = models.IntegerField(null=True, blank=True)

    # Link to tournament log (for grouping DM sends under one log entry)
    tournament_log = models.ForeignKey(
        "DiscordTournamentLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_logs",
    )

    # Manual fire tracking
    fired_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fired_discord_messages",
        help_text="User who manually fired this task (null = automatic)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "source_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=models.Q(success__isnull=True) | models.Q(success=True),
                name="uniq_discord_message_log_source_event_when_pending_or_success",
            ),
        ]

    def __str__(self):
        if self.success is None:
            state = "pending"
        elif self.success:
            state = "ok"
        else:
            state = "fail"
        return f"{self.source}:{self.source_id} → {self.channel_id} ({state})"


# ---------------------------------------------------------------------------
# Discord Event models
# ---------------------------------------------------------------------------


class ChannelType(models.TextChoices):
    TEXT = "text", "Text"
    FORUM = "forum", "Forum"
    ANNOUNCEMENT = "announcement", "Announcement"


class DMType(models.IntegerChoices):
    SIGNUP_REMINDER = 1, "Signup Reminder"
    PROFILE_UPDATE = 2, "Profile Update Required"
    ATTENDANCE_CONFIRM = 3, "Attendance Confirmation"
    TEAM_DRAFT_STARTED = 4, "Team Draft Started"
    HERO_DRAFT_STARTED = 5, "Hero Draft Started"
    TOURNAMENT_UPDATE = 6, "Tournament Update"
    EVENT_CANCELLED = 7, "Event Cancelled"


class DiscordEventMsgMixin(models.Model):
    """Abstract base for Discord messages tied to an event."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
    )
    channel_id = models.CharField(max_length=64)
    channel_type = models.CharField(
        max_length=20,
        choices=ChannelType.choices,
        default=ChannelType.TEXT,
    )
    message_id = models.CharField(max_length=64, null=True, blank=True)
    thread_id = models.CharField(max_length=64, null=True, blank=True)
    has_posted = models.BooleanField(default=False)
    message_last_updated = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DiscordEventMsgSignup(DiscordEventMsgMixin):
    """The signup post for a Discord event."""

    class Meta:
        verbose_name = "Discord Event Signup Message"
        verbose_name_plural = "Discord Event Signup Messages"

    def __str__(self):
        return f"Signup msg for event {self.event_id} (posted={self.has_posted})"


class DiscordEventMsgAnnouncement(DiscordEventMsgMixin):
    """The announcement post for a Discord event."""

    class Meta:
        verbose_name = "Discord Event Announcement Message"
        verbose_name_plural = "Discord Event Announcement Messages"

    def __str__(self):
        return f"Announcement msg for event {self.event_id} (posted={self.has_posted})"


class DiscordEvent(models.Model):
    """Links a platform Event to its Discord guild presence."""

    event = models.OneToOneField(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="discord_event",
    )
    guild_id = models.CharField(max_length=64)
    scheduled_event_id = models.CharField(max_length=64, null=True, blank=True)

    signup_message = models.OneToOneField(
        DiscordEventMsgSignup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discord_event",
    )
    announcement = models.OneToOneField(
        DiscordEventMsgAnnouncement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discord_event",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Discord Event"
        verbose_name_plural = "Discord Events"

    def __str__(self):
        return f"DiscordEvent for event {self.event_id} (guild={self.guild_id})"


class DiscordEventDM(models.Model):
    """A direct message sent to a user about a Discord event."""

    discord_event = models.ForeignKey(
        DiscordEvent,
        on_delete=models.CASCADE,
        related_name="dms",
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="discord_event_dms",
    )
    dm_type = models.IntegerField(choices=DMType.choices)
    message_id = models.CharField(max_length=64, null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered = models.BooleanField(default=False)
    responded = models.BooleanField(default=False)
    response_text = models.TextField(blank=True, default="")
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Discord Event DM"
        verbose_name_plural = "Discord Event DMs"

    def __str__(self):
        return f"DM({self.get_dm_type_display()}) → {self.org_user_id}"

    @property
    def discord_user_id(self):
        """Return the Discord user ID from the linked CustomUser."""
        return self.org_user.user.discordId

    @property
    def can_send(self):
        """Whether we can send a DM (user has a Discord ID)."""
        return bool(self.org_user.user.discordId)


class DiscordTournamentLog(models.Model):
    """Audit log for Discord notifications sent for tournaments."""

    class NotificationType(models.TextChoices):
        DRAFT_LINK = "draft_link", "Draft Link"
        HERODRAFT_LINK = "herodraft_link", "Hero Draft Link"

    class Category(models.TextChoices):
        NOTIFICATION = "notification", "Notification"
        SYSTEM = "system", "System"
        ERROR = "error", "Error"

    tournament = models.ForeignKey(
        "app.Tournament", on_delete=models.CASCADE, related_name="discord_logs"
    )
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.NOTIFICATION
    )
    notification_type = models.CharField(
        max_length=20, choices=NotificationType.choices
    )
    message = models.TextField()
    recipient_count = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Discord Tournament Log"
        verbose_name_plural = "Discord Tournament Logs"

    def __str__(self):
        return f"{self.notification_type} for tournament {self.tournament_id} ({'ok' if self.success else 'fail'})"


class LogCategory(models.IntegerChoices):
    SYSTEM = 1, "System"  # Bot-initiated: announcements, scheduled events
    INTERACTION = 2, "Interaction"  # User button clicks, selects
    SIGNUP = 3, "Signup"  # RSVP, approve, reject, confirm
    NOTIFICATION = 4, "Notification"  # Reminders, DMs


class DiscordEventLog(models.Model):
    """Audit log for Discord event API interactions."""

    discord_event = models.ForeignKey(
        DiscordEvent,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    dm = models.ForeignKey(
        DiscordEventDM,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    message_log = models.ForeignKey(
        DiscordMessageLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_logs",
        help_text="Linked outbound message with embed data and Discord API response",
    )
    category = models.IntegerField(
        choices=LogCategory.choices,
        default=LogCategory.SYSTEM,
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True, default="")
    # Discord user who triggered the action (for interaction/signup logs)
    discord_user_id = models.CharField(max_length=64, blank=True, default="")
    discord_username = models.CharField(max_length=64, blank=True, default="")
    message_id = models.CharField(max_length=64, null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Discord Event Log"
        verbose_name_plural = "Discord Event Logs"

    def __str__(self):
        return f"{self.action} ({'ok' if self.success else 'fail'}) for event {self.discord_event_id}"

    @classmethod
    def log_interaction(
        cls,
        event_id,
        action,
        discord_user_id="",
        discord_username="",
        success=True,
        error_message="",
    ):
        """Log a user interaction (button click, select, modal submit)."""
        try:
            discord_event = DiscordEvent.objects.get(event_id=event_id)
        except DiscordEvent.DoesNotExist:
            return None
        return cls.objects.create(
            discord_event=discord_event,
            category=LogCategory.INTERACTION,
            action=action,
            discord_user_id=str(discord_user_id),
            discord_username=str(discord_username),
            success=success,
            error_message=error_message,
        )

    @classmethod
    def log_signup(
        cls,
        event_id,
        action,
        discord_user_id="",
        discord_username="",
        success=True,
        error_message="",
    ):
        """Log a signup action (rsvp, approve, reject, confirm, etc.)."""
        try:
            discord_event = DiscordEvent.objects.get(event_id=event_id)
        except DiscordEvent.DoesNotExist:
            return None
        return cls.objects.create(
            discord_event=discord_event,
            category=LogCategory.SIGNUP,
            action=action,
            discord_user_id=str(discord_user_id),
            discord_username=str(discord_username),
            success=success,
            error_message=error_message,
        )
