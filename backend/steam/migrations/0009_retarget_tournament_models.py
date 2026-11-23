import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("steam", "0008_gamematchsuggestion_tier"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="gamematchsuggestion",
                    name="game",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="match_suggestions",
                        to="tournament.game",
                    ),
                ),
                migrations.AlterField(
                    model_name="gamematchsuggestion",
                    name="tournament",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="match_suggestions",
                        to="tournament.tournament",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
