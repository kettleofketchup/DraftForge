from collections.abc import Sequence
from typing import Any, cast

from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

from app.models import CustomUser
from common.game import GameType
from org.features import FeatureKey, set_org_feature
from org.settings_service import (
    EDITABLE_FIELDS,
    get_org_settings,
    normalize_warning_codes,
    update_org_settings,
    validate_retention_days,
)
from org.standing import api as standing

from .models import (
    MmrChangeRequest,
    OrgApiLimits,
    OrgApiToken,
    OrgApiTokenUsage,
    OrgFeature,
    OrgSettings,
    OrgUser,
    OrgUserGameMmr,
)

GAME_SHORT_LABELS: dict[int, str] = {GameType.DOTA2: "D2", GameType.DEADLOCK: "DL"}


def game_short_label(game_type: int) -> str:
    if game_type in GAME_SHORT_LABELS:
        return GAME_SHORT_LABELS[game_type]
    if game_type in GameType.values:
        return GameType(game_type).label
    return str(game_type)


class ReadOnlyAdminMixin:
    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class OrgUserGameMmrInline(ReadOnlyAdminMixin, admin.TabularInline):
    model = OrgUserGameMmr
    fields = ["game_type", "mmr", "updated_at", "verified_at", "verified_by"]
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(OrgUser)
class OrgUserAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "mmrs", "joined_at"]
    list_filter = ["organization"]
    search_fields = [
        "user__username",
        "user__base_profile__nickname",
        "user__discordNickname",
        "guild_nickname",
    ]
    raw_id_fields = ["user", "organization"]
    readonly_fields = ["guild_nickname"]
    inlines = [OrgUserGameMmrInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[OrgUser]:
        return super().get_queryset(request).prefetch_related("game_mmrs")

    @admin.display(description="MMRs")
    def mmrs(self, obj: OrgUser) -> str:
        by_game = {row.game_type: row.mmr for row in obj.game_mmrs.all()}
        ordered = [g for g in GameType.values if g in by_game]
        ordered += sorted(g for g in by_game if g not in GameType.values)
        return " · ".join(f"{game_short_label(g)} {by_game[g]}" for g in ordered)


@admin.register(OrgUserGameMmr)
class OrgUserGameMmrAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["org_user", "game_type", "mmr", "verified_at", "updated_at"]
    list_filter = ["game_type"]
    raw_id_fields = ["org_user"]
    readonly_fields = [
        "org_user",
        "game_type",
        "mmr",
        "updated_at",
        "verified_at",
        "verified_by",
    ]


@admin.register(MmrChangeRequest)
class MmrChangeRequestAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "subject_user",
        "organization",
        "target",
        "game_type",
        "requested_mmr",
        "status",
        "source",
        "created_at",
    ]
    list_filter = ["status", "target", "source"]
    search_fields = ["subject_user__username", "requester__username"]
    raw_id_fields = [
        "requester",
        "subject_user",
        "organization",
        "org_user",
        "league",
        "league_user",
        "reviewed_by",
    ]
    exclude = ["screenshot"]
    readonly_fields = [
        "requester",
        "subject_user",
        "organization",
        "org_user",
        "league",
        "league_user",
        "target",
        "game_type",
        "requested_mmr",
        "approved_mmr",
        "previous_mmr",
        "previous_verified",
        "has_screenshot",
        "screenshot_content_type",
        "note",
        "status",
        "source",
        "reviewed_by",
        "reviewed_at",
        "rejection_reason",
        "created_at",
        "updated_at",
    ]

    @admin.display(boolean=True, description="Screenshot")
    def has_screenshot(self, obj: MmrChangeRequest) -> bool:
        return bool(obj.screenshot.name)


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
        with transaction.atomic():
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

    def clean_signup_record_retention_days(self) -> int | None:
        try:
            return validate_retention_days(
                self.cleaned_data.get("signup_record_retention_days")
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


@admin.register(OrgSettings)
class OrgSettingsAdmin(admin.ModelAdmin):
    form = OrgSettingsAdminForm
    list_display = (
        "organization",
        "staff_override_policy",
        "signup_record_retention_days",
        "updated_at",
    )
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


@admin.register(OrgApiToken)
class OrgApiTokenAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "prefix",
        "organization",
        "user",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
    list_filter = ("revoked_at",)
    raw_id_fields = ["organization", "user", "revoked_by"]
    search_fields = ["name", "prefix", "organization__name", "user__username"]
    readonly_fields = ("prefix", "secret_hash", "created_at", "last_used_at")


@admin.register(OrgApiTokenUsage)
class OrgApiTokenUsageAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "organization",
        "user",
        "token",
        "request_count",
        "throttled_count",
    )
    list_filter = ("date",)
    raw_id_fields = ["organization", "user", "token"]
    search_fields = ["organization__name", "user__username", "token__prefix"]
    readonly_fields = (
        "token",
        "organization",
        "user",
        "date",
        "request_count",
        "throttled_count",
    )
    date_hierarchy = "date"


@admin.register(OrgApiLimits)
class OrgApiLimitsAdmin(admin.ModelAdmin):
    list_display = ("organization", "per_minute", "per_day", "updated_at", "updated_by")
    raw_id_fields = ["organization", "updated_by"]
    search_fields = ["organization__name"]
