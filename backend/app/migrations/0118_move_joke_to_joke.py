import structlog
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

log = structlog.get_logger(__name__)

JOKE_MODELS = ("joke",)


def relabel(apps: StateApps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in JOKE_MODELS:
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


def relabel_forward(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "app", "joke")


def relabel_reverse(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "joke", "app")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0117_move_user_models_to_user"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("joke", "0001_move_joke_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Joke")],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
