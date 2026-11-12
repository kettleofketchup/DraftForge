from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def backfill_timer_off(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    Tournament = apps.get_model("app", "Tournament")
    DraftOptions = apps.get_model("app", "DraftOptions")
    missing = Tournament.objects.filter(draft_options__isnull=True).values_list(
        "pk", flat=True
    )
    DraftOptions.objects.bulk_create(
        [DraftOptions(tournament_id=pk, timer_enabled=False) for pk in missing],
        batch_size=500,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0098_draftoptions_timer_enabled_default"),
    ]

    operations = [
        migrations.RunPython(backfill_timer_off, migrations.RunPython.noop),
    ]
