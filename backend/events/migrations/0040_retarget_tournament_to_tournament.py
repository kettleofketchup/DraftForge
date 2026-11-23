import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0039_alter_signupledgerentry_action"),
        ("tournament", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="event",
                    name="tournament",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_event",
                        to="tournament.tournament",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
