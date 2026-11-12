from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0100_draftevent_options_changed"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="members_private",
            field=models.BooleanField(
                default=False,
                help_text="Restrict the member list to org staff (hides it from regular members)",
            ),
        ),
    ]
