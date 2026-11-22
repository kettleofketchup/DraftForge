import django.db.models.deletion
import structlog
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

log = structlog.get_logger(__name__)

LEAGUE_MODELS = (
    "league",
    "leaguerating",
    "leaguematch",
    "leaguematchparticipant",
    "leaguelog",
)


def relabel(apps: Apps, src: str, dst: str) -> None:
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in LEAGUE_MODELS:
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
    relabel(apps, "app", "league")


def relabel_reverse(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    relabel(apps, "league", "app")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0111_move_organization_models_to_org"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("events", "0036_retarget_tournament_league_to_league"),
        ("league", "0003_move_league_models_from_app"),
        ("org", "0017_retarget_default_league_to_league"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="tournament",
                    name="league",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="league_fk_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tournaments",
                        to="league.league",
                    ),
                ),
                migrations.AlterField(
                    model_name="game",
                    name="league",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="games",
                        to="league.league",
                    ),
                ),
                migrations.DeleteModel(name="LeagueMatchParticipant"),
                migrations.DeleteModel(name="LeagueMatch"),
                migrations.DeleteModel(name="LeagueRating"),
                migrations.DeleteModel(name="LeagueLog"),
                migrations.DeleteModel(name="League"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(relabel_forward, relabel_reverse),
    ]
