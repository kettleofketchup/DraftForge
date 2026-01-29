from django.contrib import admin  # noqa: F401

# Register your models here.
from .models import CustomUser, HeroDraft, HeroDraftEvent


class CustomUserAdmin(admin.ModelAdmin):
    list_display = ["username", "mmr", "steamid", "is_superuser", "is_staff"]


class HeroDraftEventInline(admin.TabularInline):
    model = HeroDraftEvent
    extra = 0
    readonly_fields = ["event_type", "draft_team", "metadata", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
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

    def get_team_name(self, obj):
        if obj.draft_team and obj.draft_team.tournament_team:
            return obj.draft_team.tournament_team.name
        return "-"

    get_team_name.short_description = "Team"

    def get_captain(self, obj):
        if obj.draft_team and obj.draft_team.tournament_team:
            captain = obj.draft_team.tournament_team.captain
            if captain:
                return captain.username
        return "-"

    get_captain.short_description = "Captain"


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(HeroDraft, HeroDraftAdmin)
admin.site.register(HeroDraftEvent, HeroDraftEventAdmin)
