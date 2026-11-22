from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0017_retarget_default_league_to_league"),
        ("app", "0114_copy_profile_friend_ids"),
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
