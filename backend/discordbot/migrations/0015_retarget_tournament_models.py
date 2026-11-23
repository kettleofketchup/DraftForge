import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discordbot", "0014_retarget_draft_activity_teamdraft"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="discordtournamentlog",
                    name="tournament",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="discord_logs",
                        to="tournament.tournament",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
