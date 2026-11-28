from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from events.line_backfill import realign_waitlist


def forward(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    realign_waitlist(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0044_line_order_rules"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
