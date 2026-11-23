from django.contrib import admin
from django.http import HttpRequest

from app.models import TeamLog


class TeamLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "team_name",
        "team_snapshot_id",
        "action",
        "via",
        "actor",
        "target_user",
    )
    list_select_related = ("actor", "target_user", "team")
    list_filter = ("action", "via")
    search_fields = ("team_name", "reason")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: TeamLog | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: TeamLog | None = None
    ) -> bool:
        return False


admin.site.register(TeamLog, TeamLogAdmin)
