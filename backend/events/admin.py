from typing import cast

from django.contrib import admin
from django.db import transaction
from django.db.models import Model, QuerySet
from django.http import HttpRequest

from app.models import CustomUser
from events.line import waitlist_rank
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventTeam,
    EventVoicePresence,
    ReadyCheck,
    ReadyCheckEntry,
    SignupLedgerEntry,
)
from events.services import teardown_event, teardown_event_repeater


@admin.register(EventRepeater)
class EventRepeaterAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "frequency", "is_active", "created_at"]
    list_filter = ["is_active", "frequency", "organization"]

    def delete_model(self, request: HttpRequest, obj: EventRepeater) -> None:
        teardown_event_repeater(obj, actor=cast(CustomUser, request.user))

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[EventRepeater]
    ) -> None:
        actor = cast(CustomUser, request.user)
        with transaction.atomic():
            for repeater in queryset:
                teardown_event_repeater(repeater, actor=actor)


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
    readonly_fields = [
        "state",
        "host",
        "helpers",
        "contributions_awarded_at",
        "conduct_finalized_at",
    ]

    def delete_model(self, request: HttpRequest, obj: Event) -> None:
        teardown_event(
            obj, actor=cast(CustomUser, request.user), confirm_signup_records=True
        )

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Event]) -> None:
        actor = cast(CustomUser, request.user)
        with transaction.atomic():
            for event in queryset:
                teardown_event(event, actor=actor, confirm_signup_records=True)


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
        "status",
        "user",
        "event",
        "event_team",
        "signup_type",
        "waitlist_position",
        "computed_waitlist_rank",
        "signed_up_at",
        "line_seq",
        "commitment",
        "rsvp_class",
        "first_signed_up_at",
        "first_commitment",
        "first_rsvp_class",
    ]
    list_filter = ["status", "signup_type"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.display(description="Waitlist rank (line order)")
    def computed_waitlist_rank(self, obj: EventSignup) -> int | None:
        return waitlist_rank(obj)


class _ReadOnlyFieldsAdmin(admin.ModelAdmin):
    def get_readonly_fields(
        self, request: HttpRequest, obj: Model | None = None
    ) -> list[str]:
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Model | None = None
    ) -> bool:
        return request.user.is_superuser


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
    list_display = ["id", "event", "user", "present", "source", "first_joined_at"]
    list_filter = ["present", "source"]
