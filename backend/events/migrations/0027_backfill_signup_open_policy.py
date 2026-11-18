from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from events.signup_schedule import policy_from_explicit_open_at


def backfill_scheduled_policy(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Event = apps.get_model("events", "Event")
    events = list(Event.objects.filter(state="upcoming", signups_open_at__isnull=False))
    for event in events:
        for field, value in policy_from_explicit_open_at(
            event.scheduled_at, event.signups_open_at
        ).items():
            setattr(event, field, value)
    Event.objects.bulk_update(events, ["signup_open_mode", "signups_open_hours_before"])


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0026_signup_open_policy"),
    ]

    operations = [
        migrations.RunPython(backfill_scheduled_policy, migrations.RunPython.noop),
    ]
