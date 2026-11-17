from django.db import migrations


class Migration(migrations.Migration):
    """State-only: the column stays until the next release drops it."""

    dependencies = [
        ("user", "0004_backfill_game_profiles"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="baseuserprofile",
                    name="nickname",
                ),
            ],
            database_operations=[],
        ),
    ]
