from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opsnotices", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="opsnotice",
            constraint=models.UniqueConstraint(
                condition=models.Q(("last_emit_id__isnull", False)),
                fields=("organization", "key", "event_key", "dedupe_key", "last_emit_id"),
                name="opsnotice_emit_id_uniq",
            ),
        ),
    ]
