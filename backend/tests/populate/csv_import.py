"""
CSV Import test data population.

Creates an isolated organization, league, and tournament for CSV import testing.
Also creates test users that exist in the DB but are NOT members of any org.
CSV import E2E tests use these users' Steam/Discord IDs to test the import flow.

Infrastructure created:
- CSV Import Org (pk=3) - dedicated org for CSV tests
- CSV Import League (pk=3, steam_league_id=17931) - under CSV org
- CSV Import Tournament - empty tournament under CSV league
- 5 CSV test users (pk=1040-1044) - NOT in any org, added via CSV import

The site admin user (pk=1001) is added as admin of the CSV org so E2E tests
can log in and perform imports.
"""

import csv
import os

from django.utils import timezone

from app.models import CustomUser, League, Organization, PositionsModel, Tournament
from tests.data.leagues import CSV_LEAGUE
from tests.data.organizations import CSV_ORG
from tests.data.tournaments import CSV_IMPORT_TOURNAMENT
from tests.data.users import ADMIN_USER, CSV_IMPORT_USERS

# Path for CSV fixture files (repo_root/frontend/tests/playwright/fixtures/csv/)
# __file__ = backend/tests/populate/csv_import.py → 4 levels up to repo root
CSV_FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "frontend",
    "tests",
    "playwright",
    "fixtures",
    "csv",
)


def populate_csv_import_data(force=False):
    """
    Create the full CSV import test infrastructure.

    1. CSV Import Org + League (isolated from DTX/Test orgs)
    2. CSV Import Tournament (empty, under CSV league)
    3. Admin user added as org admin (for E2E access)
    4. 5 CSV test users (NOT in any org - import adds them)
    5. CSV fixture files for Playwright tests
    """
    print("Populating CSV import test data...")

    # 1. Create CSV Import Organization
    csv_org, created = Organization.objects.update_or_create(
        name=CSV_ORG.name,
        defaults={
            "description": CSV_ORG.description,
            "logo": "",
            "rules_template": CSV_ORG.rules_template,
            "timezone": CSV_ORG.timezone,
        },
    )
    print(f"  {'Created' if created else 'Updated'} organization: {CSV_ORG.name}")

    # 2. Create CSV Import League
    csv_league, created = League.objects.update_or_create(
        steam_league_id=CSV_LEAGUE.steam_league_id,
        defaults={
            "name": CSV_LEAGUE.name,
            "description": CSV_LEAGUE.description,
            "rules": CSV_LEAGUE.rules,
            "prize_pool": "",
            "timezone": CSV_LEAGUE.timezone,
        },
    )
    if csv_league.organization != csv_org:
        csv_league.organization = csv_org
        csv_league.save()
    print(f"  {'Created' if created else 'Updated'} league: {CSV_LEAGUE.name}")

    # Set as default league
    if csv_org.default_league != csv_league:
        csv_org.default_league = csv_league
        csv_org.save()

    # 3. Create CSV Import Tournament (empty)
    csv_tournament, created = Tournament.objects.update_or_create(
        name=CSV_IMPORT_TOURNAMENT.name,
        defaults={
            "date_played": timezone.now(),
            "state": CSV_IMPORT_TOURNAMENT.state,
            "tournament_type": CSV_IMPORT_TOURNAMENT.tournament_type,
            "league": csv_league,
            "steam_league_id": CSV_LEAGUE.steam_league_id,
        },
    )
    print(
        f"  {'Created' if created else 'Updated'} tournament: "
        f"{CSV_IMPORT_TOURNAMENT.name} (pk={csv_tournament.pk})"
    )

    # 4. Add admin user as org admin (so E2E tests can import)
    admin_user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if admin_user and admin_user not in csv_org.admins.all():
        csv_org.admins.add(admin_user)
        print(f"  Added {admin_user.username} as admin of {CSV_ORG.name}")

    # 5. Create CSV test users (NOT in any org)
    for user_data in CSV_IMPORT_USERS:
        existing = CustomUser.objects.filter(pk=user_data.pk).first()
        if existing and not force:
            print(f"  CSV user {user_data.username} already exists (pk={user_data.pk})")
            continue

        if existing and force:
            existing.delete()

        positions = PositionsModel.objects.create()
        user = CustomUser(
            pk=user_data.pk,
            username=user_data.username,
            nickname=user_data.nickname,
            discordId=user_data.discord_id,
            steamid=user_data.get_steam_id_64(),
            positions=positions,
        )
        user.set_unusable_password()
        user.save()
        print(f"  Created CSV user: {user_data.username} (pk={user_data.pk})")

    # 6. Generate CSV fixture files (skipped in Docker where path is inaccessible)
    _generate_csv_fixtures()

    print(
        f"CSV import test data ready. "
        f"Org: {csv_org.pk}, League: {csv_league.pk}, "
        f"Tournament: {csv_tournament.pk}"
    )


def _generate_csv_fixtures():
    """Generate CSV files for E2E tests.

    These files are also committed to git at frontend/tests/playwright/fixtures/csv/.
    This function regenerates them for fresh environments. Skipped gracefully
    in Docker where the frontend path is inaccessible from the backend container.
    """
    try:
        os.makedirs(CSV_FIXTURES_DIR, exist_ok=True)
    except PermissionError:
        print("  Skipping CSV fixture generation (path not writable, likely Docker)")
        return

    # 1. Valid CSV - known users that exist in DB (will be "added")
    valid_path = os.path.join(CSV_FIXTURES_DIR, "valid-import.csv")
    with open(valid_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "discord_id", "mmr"])
        # Row 1: Steam ID match → csv_steam_user
        writer.writerow(["76561198800000001", "", "4200"])
        # Row 2: Discord ID match → csv_discord_user
        writer.writerow(["", "300000000000000001", "3800"])
        # Row 3: Both IDs match → csv_both_ids
        writer.writerow(["76561198800000003", "300000000000000002", "5100"])
    print(f"  Generated: {valid_path}")

    # 2. CSV with errors - rows that should fail client-side validation
    errors_path = os.path.join(CSV_FIXTURES_DIR, "errors-import.csv")
    with open(errors_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "discord_id", "mmr"])
        # Row 1: Valid
        writer.writerow(["76561198800000001", "", "4200"])
        # Row 2: No identifier (error)
        writer.writerow(["", "", "5000"])
        # Row 3: Non-numeric steam ID (error)
        writer.writerow(["not_a_number", "", "3000"])
        # Row 4: Valid
        writer.writerow(["", "300000000000000001", "3800"])
    print(f"  Generated: {errors_path}")

    # 3. CSV with conflict - steam user has different discord ID on file
    conflict_path = os.path.join(CSV_FIXTURES_DIR, "conflict-import.csv")
    with open(conflict_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "discord_id", "mmr"])
        # csv_conflict_user has discord "300000000000000099" but CSV says "111111111111111111"
        writer.writerow(["76561198800000004", "111111111111111111", "4700"])
    print(f"  Generated: {conflict_path}")

    # 4. CSV with team names (for tournament import)
    teams_path = os.path.join(CSV_FIXTURES_DIR, "teams-import.csv")
    with open(teams_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "discord_id", "mmr", "team_name"])
        writer.writerow(["76561198800000001", "", "4200", "Team Radiant"])
        writer.writerow(["76561198800000003", "", "5100", "Team Radiant"])
        writer.writerow(["76561198800000005", "", "3500", "Team Dire"])
        writer.writerow(["", "300000000000000001", "3800", "Team Dire"])
    print(f"  Generated: {teams_path}")

    # 5. CSV with stub creation - unknown Steam IDs (no DB match → creates stubs)
    stubs_path = os.path.join(CSV_FIXTURES_DIR, "stubs-import.csv")
    with open(stubs_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "mmr"])
        writer.writerow(["76561198899999901", "2000"])
        writer.writerow(["76561198899999902", "2500"])
        writer.writerow(["76561198899999903", "3000"])
    print(f"  Generated: {stubs_path}")
