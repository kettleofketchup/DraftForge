import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0035_retarget_organization_to_org"),
        ("league", "0003_move_league_models_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="event",
                    name="tournament_league",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="league.league",
                    ),
                ),
                migrations.AlterField(
                    model_name="eventrepeater",
                    name="tournament_league",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="league.league",
                    ),
                ),
                migrations.AlterField(
                    model_name="orgeventdefaults",
                    name="tournament_league",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="league.league",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
