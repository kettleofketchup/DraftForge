"""Data migration to link existing tournaments to leagues."""

from django.db import migrations


def migrate_tournaments_to_leagues(apps, schema_editor):
    """
    1. Create default "DTX" Organization
    2. Create League objects for each unique steam league_id
    3. Link existing tournaments to the new League FK
    """
    Organization = apps.get_model("app", "Organization")
    League = apps.get_model("app", "League")
    Tournament = apps.get_model("app", "Tournament")

    # Step 1: Create default organization
    org, _ = Organization.objects.get_or_create(
        name="DTX", defaults={"description": "DTX Dota 2 Organization"}
    )

    # Step 2: Get unique steam_league_ids from existing tournaments
    unique_league_ids = (
        Tournament.objects.exclude(steam_league_id__isnull=True)
        .values_list("steam_league_id", flat=True)
        .distinct()
    )

    # Step 3: Create League for each unique steam league_id
    league_mapping = {}
    for steam_league_id in unique_league_ids:
        league, _ = League.objects.get_or_create(
            steam_league_id=steam_league_id,
            defaults={
                "organization": org,
                "name": f"League {steam_league_id}",
            },
        )
        league_mapping[steam_league_id] = league

    # Step 4: Link tournaments to leagues
    for tournament in Tournament.objects.exclude(steam_league_id__isnull=True):
        if tournament.steam_league_id in league_mapping:
            tournament.league = league_mapping[tournament.steam_league_id]
            tournament.save(update_fields=["league"])


def reverse_migration(apps, schema_editor):
    """Reverse: Clear league FK on tournaments (preserves org/league objects)."""
    Tournament = apps.get_model("app", "Tournament")
    Tournament.objects.update(league=None)


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0054_tournament_league_fk"),
    ]

    operations = [
        migrations.RunPython(
            migrate_tournaments_to_leagues,
            reverse_code=reverse_migration,
        ),
    ]
