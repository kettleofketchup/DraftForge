# backend/discordbot/admin.py
from django.contrib import admin

from .models import RSVP, EventTemplate, ScheduledEvent


@admin.register(EventTemplate)
class EventTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "template_type", "channel_id", "include_rsvp", "created_at"]
    list_filter = ["template_type", "include_rsvp"]
    search_fields = ["name", "title"]


@admin.register(ScheduledEvent)
class ScheduledEventAdmin(admin.ModelAdmin):
    list_display = [
        "template",
        "is_recurring",
        "day_of_week",
        "next_post_at",
        "is_active",
    ]
    list_filter = ["is_recurring", "is_active", "day_of_week"]
    raw_id_fields = ["template"]


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = [
        "scheduled_event",
        "discord_username",
        "status",
        "responded_at",
    ]
    list_filter = ["status"]
    search_fields = ["discord_username", "discord_user_id"]
    raw_id_fields = ["scheduled_event"]
