from django.contrib import admin

from opsnotices.models import OpsNotice


@admin.register(OpsNotice)
class OpsNoticeAdmin(admin.ModelAdmin):
    list_display = [
        "key",
        "category",
        "severity",
        "state",
        "organization",
        "event_name",
        "occurrences",
        "last_seen_at",
    ]
    list_filter = ["category", "severity", "state", "delivery_state"]
    raw_id_fields = ["organization", "event", "subject_user", "actor", "closed_by"]
    search_fields = ["key", "dedupe_key", "event_name"]
