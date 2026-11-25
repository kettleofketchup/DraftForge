from cacheops import invalidate_model
from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def scheduled_games_to_pending(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None
) -> None:
    Game = apps.get_model("tournament", "Game")
    Tournament = apps.get_model("tournament", "Tournament")
    if Game.objects.filter(status="scheduled").update(status="pending"):
        invalidate_model(Game)
        invalidate_model(Tournament)


class Migration(migrations.Migration):
    dependencies = [
        ("tournament", "0002_teamlog_replace_captain_set_placement"),
    ]

    operations = [
        migrations.RunPython(scheduled_games_to_pending, migrations.RunPython.noop),
    ]
