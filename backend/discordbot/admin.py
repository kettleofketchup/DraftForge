# backend/discordbot/admin.py
from django.contrib import admin
from django.http import HttpRequest

from .models import (
    RSVP,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DiscordTournamentLog,
    DraftActivityChannel,
    DraftActivityInstance,
    EventTemplate,
    ScheduledEvent,
)


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


@admin.register(DiscordMessageLog)
class DiscordMessageLogAdmin(admin.ModelAdmin):
    list_display = ["source", "source_id", "channel_id", "success", "created_at"]
    list_filter = ["source", "success"]
    readonly_fields = ["embed_data", "response_data"]


@admin.register(DiscordEvent)
class DiscordEventAdmin(admin.ModelAdmin):
    list_display = ["event", "guild_id", "scheduled_event_id", "created_at"]
    raw_id_fields = ["event", "signup_message", "announcement"]


@admin.register(DiscordEventMsgSignup)
class DiscordEventMsgSignupAdmin(admin.ModelAdmin):
    list_display = ["event", "channel_id", "channel_type", "has_posted", "created_at"]


@admin.register(DiscordEventMsgAnnouncement)
class DiscordEventMsgAnnouncementAdmin(admin.ModelAdmin):
    list_display = ["event", "channel_id", "channel_type", "has_posted", "created_at"]


@admin.register(DiscordEventLog)
class DiscordEventLogAdmin(admin.ModelAdmin):
    list_display = ["discord_event", "action", "target_type", "success", "created_at"]
    list_filter = ["action", "target_type", "success"]
    readonly_fields = ["response_data"]


@admin.register(DiscordTournamentLog)
class DiscordTournamentLogAdmin(admin.ModelAdmin):
    list_display = [
        "tournament",
        "notification_type",
        "recipient_count",
        "success",
        "created_at",
    ]
    list_filter = ["notification_type", "success"]
    readonly_fields = ["message"]


@admin.register(DiscordEventDM)
class DiscordEventDMAdmin(admin.ModelAdmin):
    list_display = [
        "discord_event",
        "org_user",
        "dm_type",
        "delivered",
        "responded",
        "created_at",
    ]
    list_filter = ["dm_type", "delivered", "responded"]


@admin.register(DraftActivityChannel)
class DraftActivityChannelAdmin(admin.ModelAdmin):
    list_display = ["guild_id", "channel_id", "draft", "team_draft"]
    search_fields = ["guild_id", "channel_id"]
    raw_id_fields = ["draft", "team_draft"]


@admin.register(DraftActivityInstance)
class DraftActivityInstanceAdmin(admin.ModelAdmin):
    list_display = ["instance_id", "guild_id", "channel_id", "draft", "team_draft"]
    search_fields = ["instance_id", "guild_id", "channel_id"]
    readonly_fields = ["instance_id", "guild_id", "channel_id", "draft", "team_draft"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
