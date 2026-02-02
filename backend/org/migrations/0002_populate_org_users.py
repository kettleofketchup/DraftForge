from django.db import migrations


def migrate_users_to_org(apps, schema_editor):
    """Create OrgUser entry for every existing user."""
    CustomUser = apps.get_model("app", "CustomUser")
    OrgUser = apps.get_model("org", "OrgUser")
    Organization = apps.get_model("app", "Organization")

    try:
        org = Organization.objects.get(pk=1)
    except Organization.DoesNotExist:
        # No org exists yet, skip migration (will run on first org creation)
        return

    for user in CustomUser.objects.all():
        OrgUser.objects.get_or_create(
            user=user,
            organization=org,
            defaults={
                "mmr": getattr(user, "mmr", 0) or 0,
                "has_active_dota_mmr": getattr(user, "has_active_dota_mmr", False),
                "dota_mmr_last_verified": getattr(user, "dota_mmr_last_verified", None),
            },
        )


def reverse_migrate(apps, schema_editor):
    """Remove all OrgUser entries (reverse migration)."""
    OrgUser = apps.get_model("org", "OrgUser")
    OrgUser.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("org", "0001_initial"),
        ("app", "0077_add_discord_server_id_to_organization"),
    ]

    operations = [
        migrations.RunPython(migrate_users_to_org, reverse_migrate),
    ]
