from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("org", "0028_promo_void_external_key")]

    operations = [
        migrations.AddField(
            model_name="externalpromotionreceipt",
            name="source_observed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
