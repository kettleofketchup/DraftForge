from django.db import migrations


class Migration(migrations.Migration):
    """State-only: the column and index stay until the next release drops them."""

    dependencies = [
        ("app", "0106_draftoptions_hero_grace_time_ms_and_more"),
        ("org", "0010_orguser_guild_nickname"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveIndex(
                    model_name="customuser",
                    name="app_customu_guildNi_602cf5_idx",
                ),
                migrations.RemoveField(
                    model_name="customuser",
                    name="guildNickname",
                ),
            ],
            database_operations=[],
        ),
    ]
