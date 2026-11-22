from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0112_move_league_models_to_league"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="steam_account_id",
            field=models.BigIntegerField(blank=True, null=True, unique=True),
        ),
    ]
