from django.contrib import admin

from .models import LeagueUser


@admin.register(LeagueUser)
class LeagueUserAdmin(admin.ModelAdmin):
    list_display = ["user", "league", "mmr", "joined_at"]
    list_filter = ["league"]
    search_fields = ["user__username", "user__nickname"]
    raw_id_fields = ["user", "org_user", "league"]
