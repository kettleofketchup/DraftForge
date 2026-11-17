from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0106_state_remove_customuser_guildnickname"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunSQL(
                    sql=[
                        'DROP INDEX IF EXISTS "app_customu_guildNi_602cf5_idx"',
                        'ALTER TABLE "app_customuser" DROP COLUMN "guildNickname"',
                    ],
                    reverse_sql=[
                        'ALTER TABLE "app_customuser" ADD COLUMN "guildNickname" text NULL',
                        'CREATE INDEX "app_customu_guildNi_602cf5_idx" '
                        'ON "app_customuser" ("guildNickname")',
                    ],
                ),
            ],
        ),
    ]
