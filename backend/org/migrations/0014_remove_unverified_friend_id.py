from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0013_conduct"),
        ("app", "0112_copy_profile_friend_ids"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="playerdeadlockprofile",
            name="unverified_friend_id",
        ),
        migrations.RemoveField(
            model_name="playerdotaprofile",
            name="unverified_friend_id",
        ),
    ]
