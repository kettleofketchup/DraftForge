from collections.abc import Sequence
from typing import Any, cast

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest

from app.models import CustomUser
from org.features import FeatureKey, set_org_feature

from .models import OrgFeature, OrgUser


@admin.register(OrgUser)
class OrgUserAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "mmr", "joined_at"]
    list_filter = ["organization"]
    search_fields = ["user__username", "user__nickname"]
    raw_id_fields = ["user", "organization"]


@admin.register(OrgFeature)
class OrgFeatureAdmin(admin.ModelAdmin):
    list_display = ["organization", "feature", "enabled", "enabled_by", "enabled_at"]
    list_filter = ["feature", "enabled"]
    raw_id_fields = ["organization"]
    readonly_fields = ["enabled_by", "enabled_at"]
    search_fields = ["organization__name"]

    def get_readonly_fields(
        self, request: HttpRequest, obj: OrgFeature | None = None
    ) -> Sequence[str]:
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            fields += ["organization", "feature"]
        return fields

    def save_model(
        self, request: HttpRequest, obj: OrgFeature, form: ModelForm, change: bool
    ) -> None:
        row = set_org_feature(
            obj.organization,
            FeatureKey(obj.feature),
            enabled=obj.enabled,
            actor=cast(CustomUser, request.user),
            notes=obj.notes,
        )
        obj.pk = row.pk
        obj.refresh_from_db()

    def has_delete_permission(
        self, request: HttpRequest, obj: OrgFeature | None = None
    ) -> bool:
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
