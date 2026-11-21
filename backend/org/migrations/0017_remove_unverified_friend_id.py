from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0016_backfill_org_user_game_mmr"),
        ("app", "0113_copy_profile_friend_ids"),
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
