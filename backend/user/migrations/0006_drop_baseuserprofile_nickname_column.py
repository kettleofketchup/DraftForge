from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0005_state_remove_baseuserprofile_nickname"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunSQL(
                    sql=['ALTER TABLE "user_baseuserprofile" DROP COLUMN "nickname"'],
                    reverse_sql=[
                        'ALTER TABLE "user_baseuserprofile" ADD COLUMN "nickname" text NULL'
                    ],
                ),
            ],
        ),
    ]
