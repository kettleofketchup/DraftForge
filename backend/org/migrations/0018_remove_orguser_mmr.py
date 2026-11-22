from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

DOTA2 = 1
BATCH = 1000


def restore_dota_column(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    OrgUser = apps.get_model("org", "OrgUser")
    OrgUserGameMmr = apps.get_model("org", "OrgUserGameMmr")
    batch: list = []
    rows = (
        OrgUserGameMmr.objects.filter(game_type=DOTA2)
        .order_by("pk")
        .values_list("org_user_id", "mmr")
        .iterator(chunk_size=BATCH)
    )
    for org_user_id, mmr in rows:
        batch.append(OrgUser(pk=org_user_id, mmr=mmr))
        if len(batch) >= BATCH:
            OrgUser.objects.bulk_update(batch, ["mmr"], batch_size=BATCH)
            batch = []
    if batch:
        OrgUser.objects.bulk_update(batch, ["mmr"], batch_size=BATCH)


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0017_retarget_default_league_to_league"),
    ]

    operations = [
        # Reverse re-adds the column, then refills it from the Dota 2 rows.
        migrations.RunPython(migrations.RunPython.noop, restore_dota_column),
        migrations.RemoveField(
            model_name="orguser",
            name="mmr",
        ),
    ]
