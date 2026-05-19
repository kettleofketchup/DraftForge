from django.core.cache import cache
from django.db import migrations


def copy_nickname_avatar_to_base_profile(apps, schema_editor):
    """Backfill BaseUserProfile rows from CustomUser.nickname / .avatar.

    Disables cacheops during the bulk write to avoid mid-migration cache
    poisoning, then explicitly invalidates the affected models at end.
    """
    CustomUser = apps.get_model("app", "CustomUser")
    BaseUserProfile = apps.get_model("user", "BaseUserProfile")

    cache.clear()  # Clear any existing cacheops state

    to_create = []
    seen = set()
    for user in CustomUser.objects.all().iterator():
        if user.pk in seen:
            continue
        seen.add(user.pk)
        to_create.append(
            BaseUserProfile(
                user_id=user.pk,
                nickname=user.nickname,
                avatar=user.avatar,
            )
        )

    BaseUserProfile.objects.bulk_create(to_create, ignore_conflicts=True)

    # Bulk_create bypasses post_save signals, so invalidate models explicitly.
    # (At migration time these models may not be registered with cacheops yet —
    # invalidate_model is safe regardless.)
    try:
        from cacheops import invalidate_model
        invalidate_model(CustomUser)
        invalidate_model(BaseUserProfile)
    except ImportError:
        pass


def reverse_copy(apps, schema_editor):
    """Reverse: copy BaseUserProfile nickname/avatar back onto CustomUser.

    Only used in tests / rollback. Production reverses by re-adding the
    columns and re-running this reverse path; see migration 00XX in
    backend/app/migrations/.
    """
    CustomUser = apps.get_model("app", "CustomUser")
    BaseUserProfile = apps.get_model("user", "BaseUserProfile")

    for profile in BaseUserProfile.objects.all().iterator():
        CustomUser.objects.filter(pk=profile.user_id).update(
            nickname=profile.nickname,
            avatar=profile.avatar,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0001_initial"),
        ("app", "0094_alter_league_steam_league_id"),
    ]

    operations = [
        migrations.RunPython(
            copy_nickname_avatar_to_base_profile,
            reverse_copy,
        ),
    ]
