from collections.abc import Sequence
from typing import Any, cast

from django import forms
from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest

from app.models import CustomUser
from org.features import FeatureKey, set_org_feature
from org.settings_service import (
    EDITABLE_FIELDS,
    get_org_settings,
    normalize_warning_codes,
    update_org_settings,
)
from org.standing import api as standing

from .models import OrgFeature, OrgSettings, OrgUser


@admin.register(OrgUser)
class OrgUserAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "mmr", "joined_at"]
    list_filter = ["organization"]
    search_fields = [
        "user__username",
        "user__base_profile__nickname",
        "user__discordNickname",
        "guild_nickname",
    ]
    raw_id_fields = ["user", "organization"]
    readonly_fields = ["guild_nickname"]


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
        standing.on_feature_toggled(
            row.organization_id, FeatureKey(row.feature), enabled=row.enabled
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


class OrgSettingsAdminForm(ModelForm):
    class Meta:
        model = OrgSettings
        fields = "__all__"

    def clean_staff_override_warning_codes(self) -> list[str]:
        try:
            return normalize_warning_codes(
                self.cleaned_data.get("staff_override_warning_codes")
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


@admin.register(OrgSettings)
class OrgSettingsAdmin(admin.ModelAdmin):
    form = OrgSettingsAdminForm
    list_display = ("organization", "staff_override_policy", "updated_at")
    list_filter = ("staff_override_policy",)
    raw_id_fields = ["organization"]
    search_fields = ["organization__name"]
    readonly_fields = ("created_at", "updated_at")

    def get_readonly_fields(
        self, request: HttpRequest, obj: OrgSettings | None = None
    ) -> Sequence[str]:
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            fields.append("organization")
        return fields

    def save_model(
        self, request: HttpRequest, obj: OrgSettings, form: ModelForm, change: bool
    ) -> None:
        row = get_org_settings(obj.organization)
        update_org_settings(
            obj.organization,
            actor=cast(CustomUser, request.user),
            changes={field: getattr(obj, field) for field in EDITABLE_FIELDS},
        )
        obj.pk = row.pk
        obj.refresh_from_db()

    def has_delete_permission(
        self, request: HttpRequest, obj: OrgSettings | None = None
    ) -> bool:
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
