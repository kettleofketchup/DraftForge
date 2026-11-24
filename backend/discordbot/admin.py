# backend/discordbot/admin.py
from datetime import timedelta

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from .models import (
    RSVP,
    DiscordDM,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DiscordTournamentLog,
    DMStatus,
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
    raw_id_fields = ["ledger_entry"]
    readonly_fields = ["ledger_entry"]


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


STUCK_SENDING_AFTER = timedelta(minutes=15)


class StuckSendingFilter(admin.SimpleListFilter):
    title = "stuck sending (>15 min)"
    parameter_name = "stuck_sending"

    def lookups(
        self, request: HttpRequest, model_admin: admin.ModelAdmin
    ) -> list[tuple[str, str]]:
        return [("yes", "Stuck sending")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[DiscordDM]
    ) -> QuerySet[DiscordDM]:
        if self.value() != "yes":
            return queryset
        return queryset.filter(
            status=DMStatus.PENDING,
            send_started_at__lt=timezone.now() - STUCK_SENDING_AFTER,
        )


@admin.register(DiscordDM)
class DiscordDMAdmin(admin.ModelAdmin):
    list_display = [
        "kind",
        "status",
        "recipient",
        "discord_user_id",
        "organization",
        "created_at",
        "sent_at",
        "click_count",
        "error_code",
    ]
    list_filter = [
        "kind",
        "status",
        "retryable",
        "organization",
        "backfilled_from",
        StuckSendingFilter,
    ]
    search_fields = [
        "idempotency_key",
        "discord_user_id",
        "discord_message_id",
        "recipient__username",
    ]
    raw_id_fields = ["recipient", "organization", "tournament_log"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: DiscordDM | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: DiscordDM | None = None
    ) -> bool:
        return False
