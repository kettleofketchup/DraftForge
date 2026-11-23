import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bracket", "0002_alter_bracketslot_bracket_and_more"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="bracketslot",
                    name="game",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="matches",
                        to="tournament.game",
                    ),
                ),
                migrations.AlterField(
                    model_name="bracketslot",
                    name="participant",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="match_slots",
                        to="tournament.team",
                    ),
                ),
                migrations.AlterField(
                    model_name="tournamentbracket",
                    name="tournament",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brackets",
                        to="tournament.tournament",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
