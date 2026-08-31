from django.contrib import admin

from .models import BaseUserProfile, DeadlockUserProfile, DotaUserProfile


@admin.register(BaseUserProfile)
class BaseUserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nickname", "avatar")
    search_fields = ("user__username", "nickname")
    raw_id_fields = ("user",)


@admin.register(DotaUserProfile)
class DotaUserProfileAdmin(admin.ModelAdmin):
    list_display = ("base_profile", "positions", "has_active_dota_mmr",
                    "dota_mmr_last_verified")
    search_fields = ("base_profile__user__username",)
    raw_id_fields = ("base_profile", "positions")


@admin.register(DeadlockUserProfile)
class DeadlockUserProfileAdmin(admin.ModelAdmin):
    list_display = ("base_profile", "rank", "rank_date")
    search_fields = ("base_profile__user__username", "rank")
    raw_id_fields = ("base_profile",)
