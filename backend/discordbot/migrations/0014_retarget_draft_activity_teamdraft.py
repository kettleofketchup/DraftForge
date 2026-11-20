import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discordbot", "0013_retarget_draft_activity_herodraft"),
        ("draft", "0002_move_team_draft_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="draftactivitychannel",
                    name="team_draft",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="draft.draft",
                    ),
                ),
                migrations.AlterField(
                    model_name="draftactivityinstance",
                    name="team_draft",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="draft.draft",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
