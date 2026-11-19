from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

READY_CHECK_MAX_MINUTES = 1440
MODELS: tuple[str, ...] = ("Event", "EventRepeater", "OrgEventDefaults")


def backfill(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    for name in MODELS:
        model = apps.get_model("events", name)
        batch = []
        for row in model.objects.only(
            "pk", "discord_confirm_attendance_hours"
        ).iterator():
            hours = row.discord_confirm_attendance_hours
            if hours is None or hours < 1:
                continue
            row.ready_check_open_minutes = min(hours * 60, READY_CHECK_MAX_MINUTES)
            batch.append(row)
        model.objects.bulk_update(batch, ["ready_check_open_minutes"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0028_ready_check_settings"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
