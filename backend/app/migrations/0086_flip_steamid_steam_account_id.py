"""
Flip-flop steamid ↔ steam_account_id.

Previously: steamid (64-bit BigInteger) was the primary field, steam_account_id
was auto-computed. In production, steamid was sometimes used to store 32-bit
friend codes directly.

After this migration:
  - steam_account_id (32-bit Friend ID) is the primary unique field
  - steamid (64-bit Steam ID) is auto-computed from steam_account_id in save()

Data handling:
  - steamid >= BASE → already 64-bit → steam_account_id = steamid - BASE
  - steamid < BASE  → 32-bit friend code → steam_account_id = steamid,
                                             steamid = steamid + BASE
"""

from django.db import migrations, models

STEAM_ID_64_BASE = 76561197960265728


def flip_steam_ids(apps, schema_editor):
    CustomUser = apps.get_model("app", "CustomUser")

    users = CustomUser.objects.filter(steamid__isnull=False).exclude(steamid=0)
    updated = 0

    for user in users:
        if user.steamid >= STEAM_ID_64_BASE:
            # Already 64-bit: compute 32-bit account ID
            user.steam_account_id = user.steamid - STEAM_ID_64_BASE
        else:
            # 32-bit friend code stored in steamid: flip-flop
            user.steam_account_id = user.steamid
            user.steamid = user.steamid + STEAM_ID_64_BASE

        user.save(update_fields=["steamid", "steam_account_id"])
        updated += 1

    if updated > 0:
        print(f"  Normalized {updated} users: steam_account_id is now primary")


def reverse_flip(apps, schema_editor):
    """Reverse: restore steamid as primary, clear steam_account_id."""
    CustomUser = apps.get_model("app", "CustomUser")
    # steam_account_id values are correct 32-bit, steamid is correct 64-bit
    # Just swap the unique constraints back (schema changes are auto-reversed)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0085_merge_20260209_1934"),
    ]

    operations = [
        # Step 1: Data migration - normalize all values
        migrations.RunPython(flip_steam_ids, reverse_flip),
        # Step 2: Drop unique on steamid (must happen before adding unique on steam_account_id
        # in case of overlapping constraint checks)
        migrations.AlterField(
            model_name="customuser",
            name="steamid",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        # Step 3: Make steam_account_id unique (the new primary identifier)
        migrations.AlterField(
            model_name="customuser",
            name="steam_account_id",
            field=models.IntegerField(blank=True, null=True, unique=True),
        ),
    ]
