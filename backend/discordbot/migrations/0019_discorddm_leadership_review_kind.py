from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discordbot", "0018_backfill_discord_dm_ledger"),
    ]

    operations = [
        migrations.AlterField(
            model_name="discorddm",
            name="kind",
            field=models.CharField(
                choices=[
                    ("signup_reminder", "Signup Reminder"),
                    ("tournament_draft_link", "Tournament Draft Link"),
                    ("tournament_herodraft_link", "Tournament Herodraft Link"),
                    ("lobby_info", "Lobby Info"),
                    ("signup_confirmation", "Signup Confirmation"),
                    ("leadership_review", "Leadership Review"),
                    ("test_notification", "Test Notification"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="discorddm",
            name="subject_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("event", "Event"),
                    ("tournament", "Tournament"),
                    ("game_lobby", "Game Lobby"),
                    ("captain_snapshot", "Captain Snapshot"),
                ],
                max_length=32,
            ),
        ),
    ]
