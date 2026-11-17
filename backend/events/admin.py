from django.contrib import admin
from django.db.models import Model
from django.http import HttpRequest

from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventTeam,
    EventVoicePresence,
    ReadyCheck,
    ReadyCheckEntry,
)


@admin.register(EventRepeater)
class EventRepeaterAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "frequency", "is_active", "created_at"]
    list_filter = ["is_active", "frequency", "organization"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "organization",
        "scheduled_at",
        "ends_at",
        "state",
        "created_at",
    ]
    list_filter = ["state", "organization"]
    readonly_fields = ["state", "host", "helpers", "contributions_awarded_at"]


@admin.register(EventTeam)
class EventTeamAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "captain", "created_at"]


@admin.register(EventSignup)
class EventSignupAdmin(admin.ModelAdmin):
    list_display = ["user", "event", "signup_type", "status", "created_at"]
    list_filter = ["status", "signup_type"]


class _ReadOnlyFieldsAdmin(admin.ModelAdmin):
    def get_readonly_fields(
        self, request: HttpRequest, obj: Model | None = None
    ) -> list[str]:
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(ReadyCheck)
class ReadyCheckAdmin(_ReadOnlyFieldsAdmin):
    list_display = ["id", "event", "phase", "outcome", "opened_at"]
    list_filter = ["phase", "outcome"]


@admin.register(ReadyCheckEntry)
class ReadyCheckEntryAdmin(_ReadOnlyFieldsAdmin):
    list_display = ["id", "ready_check", "user", "state", "confirmed_via"]
    list_filter = ["state", "confirmed_via"]


@admin.register(EventVoicePresence)
class EventVoicePresenceAdmin(_ReadOnlyFieldsAdmin):
    list_display = ["id", "event", "user", "present", "first_joined_at"]
    list_filter = ["present"]
