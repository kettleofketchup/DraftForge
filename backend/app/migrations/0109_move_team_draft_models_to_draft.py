from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from telemetry.logging import get_logger

log = get_logger(__name__)

TEAM_MODELS = ("draft", "draftround", "draftevent", "draftoptions")


def relabel(apps: Apps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in TEAM_MODELS:
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
        ("app", "0108_move_hero_draft_models_to_draft"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("discordbot", "0014_retarget_draft_activity_teamdraft"),
        ("draft", "0004_move_team_draft_models"),
        ("events", "0024_backfill_event_draft_options"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="draft", name="tournament"),
                migrations.RemoveField(model_name="draftevent", name="draft"),
                migrations.RemoveField(model_name="draftround", name="draft"),
                migrations.RemoveField(model_name="draftevent", name="actor"),
                migrations.RemoveField(model_name="draftoptions", name="tournament"),
                migrations.RemoveField(model_name="draftround", name="captain"),
                migrations.RemoveField(model_name="draftround", name="choice"),
                migrations.DeleteModel(name="DraftEvent"),
                migrations.DeleteModel(name="DraftRound"),
                migrations.DeleteModel(name="Draft"),
                migrations.DeleteModel(name="DraftOptions"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
