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
    day_of_week = models.IntegerField(null=True, blank=True)  # 0=Monday, 6=Sunday
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
