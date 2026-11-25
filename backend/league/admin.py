from django.contrib import admin

from .models import LeagueUser


@admin.register(LeagueUser)
class LeagueUserAdmin(admin.ModelAdmin):
    list_display = ["user", "league", "mmr", "mmr_verified_at", "joined_at"]
    list_filter = ["league"]
    search_fields = [
        "user__username",
        "user__base_profile__nickname",
        "user__discordNickname",
        "org_user__guild_nickname",
    ]
    raw_id_fields = ["user", "org_user", "league"]
    readonly_fields = ["mmr_verified_at", "mmr_verified_by"]
