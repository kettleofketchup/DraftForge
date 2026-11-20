from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

DOTA2 = 1
BATCH = 1000
MMR_MIN = 0
MMR_MAX = 20000


def backfill_dota_rows(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    OrgUser = apps.get_model("org", "OrgUser")
    OrgUserGameMmr = apps.get_model("org", "OrgUserGameMmr")
    created = 0
    out_of_range: list[int] = []
    batch: list = []
    rows = (
        OrgUser.objects.exclude(mmr=0)
        .order_by("pk")
        .values_list("pk", "mmr")
        .iterator(chunk_size=BATCH)
    )
    for pk, mmr in rows:
        if not MMR_MIN <= mmr <= MMR_MAX:
            out_of_range.append(pk)
        batch.append(OrgUserGameMmr(org_user_id=pk, game_type=DOTA2, mmr=mmr))
        if len(batch) >= BATCH:
            OrgUserGameMmr.objects.bulk_create(
                batch, batch_size=BATCH, ignore_conflicts=True
            )
            created += len(batch)
            batch = []
    if batch:
        OrgUserGameMmr.objects.bulk_create(
            batch, batch_size=BATCH, ignore_conflicts=True
        )
        created += len(batch)
    print(f"\n  org_user_game_mmr backfill: {created} Dota 2 rows")
    if out_of_range:
        print(
            f"  WARNING: {len(out_of_range)} OrgUser mmr values outside "
            f"{MMR_MIN}..{MMR_MAX} copied verbatim; OrgUser pks: {out_of_range}"
        )


def restore_orguser_mmr(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    OrgUser = apps.get_model("org", "OrgUser")
    OrgUserGameMmr = apps.get_model("org", "OrgUserGameMmr")
    OrgUser.objects.exclude(mmr=0).update(mmr=0)
    restored = 0
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
            restored += len(batch)
            batch = []
    if batch:
        OrgUser.objects.bulk_update(batch, ["mmr"], batch_size=BATCH)
        restored += len(batch)
    print(f"\n  org_user_game_mmr reverse: restored {restored} OrgUser.mmr values")


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0013_orgusergamemmr"),
    ]

    operations = [
        migrations.RunPython(backfill_dota_rows, restore_orguser_mmr),
    ]
