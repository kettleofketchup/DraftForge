import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opsnotices", "0002_opsnotice_emit_id_uniq"),
        ("org", "0014_move_organization_models_from_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="opsnotice",
                    name="organization",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ops_notices",
                        to="org.organization",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
