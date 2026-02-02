from django.contrib import admin

from .models import OrgUser


@admin.register(OrgUser)
class OrgUserAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "mmr", "joined_at"]
    list_filter = ["organization"]
    search_fields = ["user__username", "user__nickname"]
    raw_id_fields = ["user", "organization"]
