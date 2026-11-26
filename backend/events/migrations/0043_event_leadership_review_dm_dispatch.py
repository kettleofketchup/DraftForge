from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def fence_existing_events(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    event = apps.get_model("events", "Event")
    snapshot = apps.get_model("org", "EventCaptain")
    snapshot_events = snapshot.objects.using(schema_editor.connection.alias).values("event_id")
    event.objects.using(schema_editor.connection.alias).filter(
        models.Q(state__in=["completed", "cancelled"]) | models.Q(pk__in=snapshot_events)
    ).update(leadership_review_dm_dispatch={})


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0042_eventsignup_self_made"),
        ("org", "0026_leadership_review_dms"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="leadership_review_dm_dispatch",
            field=models.JSONField(default=None, editable=False, null=True),
        ),
        migrations.RunPython(fence_existing_events, migrations.RunPython.noop),
    ]
