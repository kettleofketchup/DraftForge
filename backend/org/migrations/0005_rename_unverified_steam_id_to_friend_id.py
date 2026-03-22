# Rename unverified_steam_id → unverified_friend_id on both profile models

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("org", "0004_playerdotaprofile_battlecup_screenshot_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="playerdotaprofile",
            old_name="unverified_steam_id",
            new_name="unverified_friend_id",
        ),
        migrations.RenameField(
            model_name="playerdeadlockprofile",
            old_name="unverified_steam_id",
            new_name="unverified_friend_id",
        ),
    ]
