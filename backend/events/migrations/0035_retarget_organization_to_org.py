import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0034_event_conduct_finalized_at"),
        ("org", "0014_move_organization_models_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="eventrepeater",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="event_repeaters",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="event",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="orgeventdefaults",
                    name="organization",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="event_defaults",
                        to="org.organization",
                    ),
                ),
                migrations.AlterField(
                    model_name="signupledgerentry",
                    name="organization",
                    field=models.ForeignKey(
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="org.organization",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
