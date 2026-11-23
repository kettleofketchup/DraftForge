import structlog
from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

log = structlog.get_logger(__name__)

TOURNAMENT_MODELS = ("tournament", "team", "game", "teamlog")


def relabel(apps: Apps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in TOURNAMENT_MODELS:
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
    relabel(apps, "app", "tournament")


def relabel_reverse(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "tournament", "app")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0114_copy_profile_friend_ids"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("tournament", "0001_initial"),
        ("bracket", "0003_retarget_tournament_models"),
        ("discordbot", "0015_retarget_tournament_models"),
        ("draft", "0006_retarget_tournament_models"),
        ("events", "0039_retarget_tournament_to_tournament"),
        ("league", "0004_retarget_leaguematch_game"),
        ("lobby", "0005_retarget_tournament_models"),
        ("org", "0021_retarget_tournament_models"),
        ("steam", "0009_retarget_tournament_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="TeamLog"),
                migrations.DeleteModel(name="Game"),
                migrations.RemoveField(model_name="tournament", name="winning_team"),
                migrations.DeleteModel(name="Team"),
                migrations.DeleteModel(name="Tournament"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
