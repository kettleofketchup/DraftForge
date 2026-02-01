from django.db import migrations


def migrate_tournament_users_to_league(apps, schema_editor):
    """Create LeagueUser entries for users in tournaments with leagues."""
    Tournament = apps.get_model("app", "Tournament")
    OrgUser = apps.get_model("org", "OrgUser")
    LeagueUser = apps.get_model("league", "LeagueUser")

    for tournament in Tournament.objects.select_related("league").prefetch_related(
        "users"
    ):
        league = tournament.league
        if not league:
            continue

        # Get the organization for this league
        org = league.organizations.first()
        if not org:
            continue

        for user in tournament.users.all():
            try:
                org_user = OrgUser.objects.get(user=user, organization=org)
            except OrgUser.DoesNotExist:
                # User doesn't have an OrgUser entry for this org, skip
                continue

            LeagueUser.objects.get_or_create(
                user=user,
                league=league,
                defaults={
                    "org_user": org_user,
                    "mmr": org_user.mmr,
                },
            )


def reverse_migrate(apps, schema_editor):
    """Remove all LeagueUser entries (reverse migration)."""
    LeagueUser = apps.get_model("league", "LeagueUser")
    LeagueUser.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0001_initial"),
        ("org", "0002_populate_org_users"),
    ]

    operations = [
        migrations.RunPython(migrate_tournament_users_to_league, reverse_migrate),
    ]
