import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discordbot", "0012_draftactivitychannel_draftactivityinstance"),
        ("draft", "0001_move_hero_draft_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="draftactivitychannel",
                    name="draft",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="draft.herodraft",
                    ),
                ),
                migrations.AlterField(
                    model_name="draftactivityinstance",
                    name="draft",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="draft.herodraft",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
