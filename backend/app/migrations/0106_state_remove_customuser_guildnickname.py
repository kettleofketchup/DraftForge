from django.db import migrations


class Migration(migrations.Migration):
    """State-only: the column and index stay until the next release drops them."""

    dependencies = [
        ("app", "0105_orglog_reopen_event"),
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
