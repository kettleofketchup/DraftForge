from django.contrib import admin
from django.http import HttpRequest

from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventTeam,
    SignupLedgerEntry,
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


@admin.register(SignupLedgerEntry)
class SignupLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "event_id",
        "subject_user",
        "action",
        "actor_role",
        "means",
        "correlation_id",
    )
    list_select_related = ("subject_user", "actor_user")
    list_filter = ("action", "actor_role", "means")
    search_fields = ("correlation_id",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: SignupLedgerEntry | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: SignupLedgerEntry | None = None
    ) -> bool:
        return False


@admin.register(EventSignup)
class EventSignupAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "event",
        "signup_type",
        "status",
        "created_at",
        "line_seq",
        "commitment",
        "signed_up_at",
    ]
    readonly_fields = [
        "signed_up_at",
        "line_seq",
        "commitment",
        "rsvp_class",
        "first_signed_up_at",
        "first_commitment",
        "first_rsvp_class",
    ]
    list_filter = ["status", "signup_type"]
