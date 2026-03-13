from django.contrib import admin

from events.models import Event, EventRepeater, EventSignup, EventTeam


@admin.register(EventRepeater)
class EventRepeaterAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "frequency", "is_active", "created_at"]
    list_filter = ["is_active", "frequency", "organization"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "scheduled_at", "state", "created_at"]
    list_filter = ["state", "organization"]


@admin.register(EventTeam)
class EventTeamAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "captain", "created_at"]


@admin.register(EventSignup)
class EventSignupAdmin(admin.ModelAdmin):
    list_display = ["user", "event", "signup_type", "status", "created_at"]
    list_filter = ["status", "signup_type"]
