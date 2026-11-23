import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0003_move_league_models_from_app"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="leaguematch",
                    name="game",
                    field=models.OneToOneField(
                        blank=True,
                        help_text="Link to Game model if applicable",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="league_match",
                        to="tournament.game",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
