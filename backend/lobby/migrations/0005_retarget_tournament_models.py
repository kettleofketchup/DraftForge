import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lobby", "0004_gamelobby_password"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="gamelobby",
                    name="dire_team",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tournament.team",
                    ),
                ),
                migrations.AlterField(
                    model_name="gamelobby",
                    name="game",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lobbies",
                        to="tournament.game",
                    ),
                ),
                migrations.AlterField(
                    model_name="gamelobby",
                    name="provisional_winner_team",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tournament.team",
                    ),
                ),
                migrations.AlterField(
                    model_name="gamelobby",
                    name="radiant_team",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tournament.team",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
