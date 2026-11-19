from datetime import timedelta

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

MAX_HOURS_BEFORE = 24 * 60


def backfill_scheduled_policy(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Event = apps.get_model("events", "Event")
    events = list(Event.objects.filter(state="upcoming", signups_open_at__isnull=False))
    for event in events:
        hours = round((event.scheduled_at - event.signups_open_at) / timedelta(hours=1))
        event.signup_open_mode = "scheduled"
        event.signups_open_hours_before = min(max(hours, 0), MAX_HOURS_BEFORE)
    Event.objects.bulk_update(events, ["signup_open_mode", "signups_open_hours_before"])


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0030_signup_open_policy"),
    ]

    operations = [
        migrations.RunPython(backfill_scheduled_policy, migrations.RunPython.noop),
    ]
