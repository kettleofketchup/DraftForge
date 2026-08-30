from django.db import migrations


def backfill_game_profiles(apps, schema_editor):
    # Defensive cache clear (mirrors T1 user/0002): django-redis hard-fails on
    # Redis-down, unlike cacheops which degrades. Wrap so cold-start / broken-
    # Redis CI doesn't fail the migration.
    from django.core.cache import cache

    try:
        cache.clear()
    except Exception:
        pass

    CustomUser = apps.get_model("app", "CustomUser")
    BaseUserProfile = apps.get_model("user", "BaseUserProfile")
    DotaUserProfile = apps.get_model("user", "DotaUserProfile")
    DeadlockUserProfile = apps.get_model("user", "DeadlockUserProfile")

    dota_to_create = []
    deadlock_to_create = []
    # CustomUser still has positions / has_active_dota_mmr / dota_mmr_last_verified
    # columns at this migration (they drop in app/0096, which depends on this).
    for user in CustomUser.objects.all().iterator(chunk_size=1000):
        bp, _ = BaseUserProfile.objects.get_or_create(user_id=user.pk)
        if not DotaUserProfile.objects.filter(base_profile_id=bp.pk).exists():
            dota_to_create.append(
                DotaUserProfile(
                    base_profile_id=bp.pk,
                    positions_id=user.positions_id,
                    has_active_dota_mmr=user.has_active_dota_mmr,
                    dota_mmr_last_verified=user.dota_mmr_last_verified,
                )
            )
        if not DeadlockUserProfile.objects.filter(base_profile_id=bp.pk).exists():
            deadlock_to_create.append(DeadlockUserProfile(base_profile_id=bp.pk))

    DotaUserProfile.objects.bulk_create(dota_to_create, ignore_conflicts=True)
    DeadlockUserProfile.objects.bulk_create(deadlock_to_create, ignore_conflicts=True)

    # bulk_create bypasses post_save signals — invalidate explicitly (lesson:
    # bulk_update/bulk_create invariant).
    try:
        from cacheops import invalidate_model

        invalidate_model(CustomUser)
        invalidate_model(BaseUserProfile)
        invalidate_model(DotaUserProfile)
        invalidate_model(DeadlockUserProfile)
    except ImportError:
        pass


def reverse_backfill(apps, schema_editor):
    # Copy positions/mmr back onto CustomUser before app/0096 re-adds the columns.
    CustomUser = apps.get_model("app", "CustomUser")
    DotaUserProfile = apps.get_model("user", "DotaUserProfile")
    for dota in (
        DotaUserProfile.objects.all()
        .select_related("base_profile")
        .iterator(chunk_size=1000)
    ):
        CustomUser.objects.filter(pk=dota.base_profile.user_id).update(
            positions_id=dota.positions_id,
            has_active_dota_mmr=dota.has_active_dota_mmr,
            dota_mmr_last_verified=dota.dota_mmr_last_verified,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0003_dota_deadlock_user_profiles"),
    ]
    operations = [
        migrations.RunPython(backfill_game_profiles, reverse_backfill),
    ]
