from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0031_mmrchangerequest_screenshot_purged_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="orgleadershipsettings",
            name="captain_feedback_visible",
            field=models.BooleanField(default=True),
        ),
    ]
