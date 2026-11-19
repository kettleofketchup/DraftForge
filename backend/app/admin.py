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

from .models import CustomUser


class CustomUserAdmin(admin.ModelAdmin):
    list_display = ["username", "steamid", "is_superuser", "is_staff"]
    readonly_fields = ["discordNickname"]
    exclude = ["guildNickname"]

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


admin.site.register(CustomUser, CustomUserAdmin)
