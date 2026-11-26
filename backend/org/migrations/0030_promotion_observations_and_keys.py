import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("org", "0029_receipt_source_observed_at")]

    operations = [
        migrations.CreateModel(
            name="PromotionImportObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(default="contact_log", max_length=32)),
                ("after", models.BigIntegerField()),
                ("through", models.BigIntegerField()),
                ("observed_at", models.DateTimeField()),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="org.organization")),
            ],
            options={
                "constraints": [models.CheckConstraint(condition=models.Q(("through__gt", models.F("after"))), name="promotion_observation_nonempty")],
            },
        ),
        migrations.CreateModel(
            name="PromotionSendExternalKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("discord_id", models.CharField(max_length=20)),
                ("send", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="external_point_keys", to="org.promosend")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("send", "discord_id"), name="promotion_send_external_key_unique")],
            },
        ),
    ]
