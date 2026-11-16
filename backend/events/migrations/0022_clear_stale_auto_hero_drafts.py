from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# Events in these states have not finished, so their tournaments still want
# auto-created hero drafts; any undrafted backlog belongs to everything else.
OPEN_EVENT_STATES = ["upcoming", "signups_open", "roll_call", "in_progress"]


def clear_stale_flags(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Tournament = apps.get_model("app", "Tournament")
    Tournament.objects.filter(auto_create_hero_drafts=True).exclude(
        state="past"
    ).exclude(source_event__state__in=OPEN_EVENT_STATES).update(
        auto_create_hero_drafts=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0105_orglog_reopen_event"),
        ("events", "0021_event_end_and_staff"),
    ]

    operations = [
        migrations.RunPython(clear_stale_flags, migrations.RunPython.noop),
    ]
