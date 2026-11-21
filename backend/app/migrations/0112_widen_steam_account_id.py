from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0111_move_organization_models_to_org"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="steam_account_id",
            field=models.BigIntegerField(blank=True, null=True, unique=True),
        ),
    ]
