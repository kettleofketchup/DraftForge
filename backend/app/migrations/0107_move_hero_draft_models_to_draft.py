from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from telemetry.logging import get_logger

log = get_logger(__name__)

HERO_MODELS = ("herodraft", "draftteam", "herodraftround", "herodraftevent")


def relabel(apps: Apps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in HERO_MODELS:
        source = content_type.objects.filter(app_label=src, model=model)
        if content_type.objects.filter(app_label=dst, model=model).exists():
            if source.exists():
                log.warning(
                    "contenttype_relabel_skipped",
                    system="migrations",
                    subsystem="contenttypes",
                    model=model,
                    direction=f"{src}->{dst}",
                )
            continue
        source.update(app_label=dst)


def relabel_forward(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "app", "draft")


def relabel_reverse(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "draft", "app")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0106_draftoptions_hero_grace_time_ms_and_more"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("discordbot", "0013_retarget_draft_activity_herodraft"),
        ("draft", "0001_move_hero_draft_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="herodraftevent", name="draft_team"),
                migrations.RemoveField(model_name="herodraft", name="roll_winner"),
                migrations.RemoveField(model_name="herodraftround", name="draft_team"),
                migrations.RemoveField(model_name="herodraft", name="game"),
                migrations.RemoveField(model_name="herodraftevent", name="draft"),
                migrations.RemoveField(model_name="herodraftround", name="draft"),
                migrations.DeleteModel(name="DraftTeam"),
                migrations.DeleteModel(name="HeroDraftEvent"),
                migrations.DeleteModel(name="HeroDraft"),
                migrations.DeleteModel(name="HeroDraftRound"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
