from collections.abc import Sequence
from typing import Any

from django.contrib import admin
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.text import capfirst

from org.contributions.services import delete_user_entries
from org.models import ContributionEntry
from org.promotion.services import release_earning_sends

from .models import CustomUser, HeroDraft, HeroDraftEvent


class CustomUserAdmin(admin.ModelAdmin):
    list_display = ["username", "steamid", "is_superuser", "is_staff"]

    def get_deleted_objects(
        self, objs: Sequence[CustomUser] | QuerySet[CustomUser], request: HttpRequest
    ) -> tuple[list[Any], dict[str, int], set[str], list[str]]:
        to_delete, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request
        )
        opts = ContributionEntry._meta
        prefix = f"{capfirst(opts.verbose_name)}: "
        protected = [item for item in protected if not str(item).startswith(prefix)]
        entries = list(
            ContributionEntry.objects.nocache().filter(
                org_user__user__in=[obj.pk for obj in objs]
            )
        )
        if entries:
            to_delete = [*to_delete, *(f"{prefix}{entry}" for entry in entries)]
            model_count = {**model_count, opts.verbose_name_plural: len(entries)}
            if not request.user.has_perm(f"{opts.app_label}.delete_{opts.model_name}"):
                perms_needed = {*perms_needed, opts.verbose_name}
        return to_delete, model_count, perms_needed, protected

    def delete_model(self, request: HttpRequest, obj: CustomUser) -> None:
        with transaction.atomic():
            release_earning_sends(obj)
            delete_user_entries(obj, actor=request.user)
            super().delete_model(request, obj)

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[CustomUser]
    ) -> None:
        with transaction.atomic():
            for user in queryset:
                release_earning_sends(user)
                delete_user_entries(user, actor=request.user)
            super().delete_queryset(request, queryset)


class HeroDraftEventInline(admin.TabularInline):
    model = HeroDraftEvent
    extra = 0
    readonly_fields = ["event_type", "draft_team", "metadata", "created_at"]
    can_delete = False

    def has_add_permission(
        self, request: HttpRequest, obj: HeroDraft | None = None
    ) -> bool:
        return False


class HeroDraftAdmin(admin.ModelAdmin):
    list_display = ["id", "game", "state", "created_at", "updated_at"]
    list_filter = ["state", "created_at"]
    search_fields = ["id", "game__id"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [HeroDraftEventInline]


class HeroDraftEventAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "draft",
        "event_type",
        "get_team_name",
        "get_captain",
        "created_at",
    ]
    list_filter = ["event_type", "created_at"]
    search_fields = ["draft__id", "draft_team__tournament_team__name"]
    readonly_fields = ["draft", "event_type", "draft_team", "metadata", "created_at"]
    date_hierarchy = "created_at"

    def get_team_name(self, obj: HeroDraftEvent) -> str:
        if obj.draft_team and obj.draft_team.tournament_team:
            return obj.draft_team.tournament_team.name
        return "-"

    get_team_name.short_description = "Team"

    def get_captain(self, obj: HeroDraftEvent) -> str:
        if obj.draft_team and obj.draft_team.tournament_team:
            captain = obj.draft_team.tournament_team.captain
            if captain:
                return captain.username
        return "-"

    get_captain.short_description = "Captain"


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(HeroDraft, HeroDraftAdmin)
admin.site.register(HeroDraftEvent, HeroDraftEventAdmin)
