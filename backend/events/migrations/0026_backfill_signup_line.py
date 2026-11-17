from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from events.line_backfill import backfill_signup_line, unbackfill_signup_line


def forward(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    backfill_signup_line(apps)


def reverse(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    unbackfill_signup_line(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0025_signup_ledger"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
