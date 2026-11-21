from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0110_orglog_conduct_actions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="steam_account_id",
            field=models.BigIntegerField(blank=True, null=True, unique=True),
        ),
    ]
