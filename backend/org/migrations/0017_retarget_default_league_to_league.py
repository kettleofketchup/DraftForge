import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0016_backfill_org_user_game_mmr"),
        ("league", "0003_move_league_models_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="organization",
                    name="default_league",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="default_for_organization",
                        to="league.league",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
