"""
CSV Import test data population.

Creates users that exist in the database but are NOT members of any organization.
CSV import E2E tests use these users' Steam/Discord IDs to test the import flow.

Also generates CSV fixture files at known paths for Playwright tests.
"""

import csv
import os

from app.models import CustomUser, PositionsModel
from tests.data.users import CSV_IMPORT_USERS

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


def populate_csv_import_users(force=False):
    """
    Create CSV import test users.

    These users have known Steam/Discord IDs but are NOT added to any org.
    The CSV import flow will add them.

    Also creates CSV fixture files for E2E tests.
    """
    print("Populating CSV import test users...")

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
            mmr=user_data.mmr or 3000,
            positions=positions,
        )
        user.set_unusable_password()
        user.save()
        print(f"  Created CSV user: {user_data.username} (pk={user_data.pk})")

    # Generate CSV fixture files
    _generate_csv_fixtures()

    print("CSV import test data ready.")


def _generate_csv_fixtures():
    """Generate CSV files for E2E tests."""
    os.makedirs(CSV_FIXTURES_DIR, exist_ok=True)

    # 1. Valid CSV - known users that exist in DB (will be "added")
    valid_path = os.path.join(CSV_FIXTURES_DIR, "valid-import.csv")
    with open(valid_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "discord_id", "base_mmr"])
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
        writer.writerow(["steam_friend_id", "discord_id", "base_mmr"])
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
        writer.writerow(["steam_friend_id", "discord_id", "base_mmr"])
        # csv_conflict_user has discord "300000000000000099" but CSV says "111111111111111111"
        writer.writerow(["76561198800000004", "111111111111111111", "4700"])
    print(f"  Generated: {conflict_path}")

    # 4. CSV with team names (for tournament import)
    teams_path = os.path.join(CSV_FIXTURES_DIR, "teams-import.csv")
    with open(teams_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "discord_id", "base_mmr", "team_name"])
        writer.writerow(["76561198800000001", "", "4200", "Team Radiant"])
        writer.writerow(["76561198800000003", "", "5100", "Team Radiant"])
        writer.writerow(["76561198800000005", "", "3500", "Team Dire"])
        writer.writerow(["", "300000000000000001", "3800", "Team Dire"])
    print(f"  Generated: {teams_path}")

    # 5. CSV with stub creation - unknown Steam IDs (no DB match → creates stubs)
    stubs_path = os.path.join(CSV_FIXTURES_DIR, "stubs-import.csv")
    with open(stubs_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["steam_friend_id", "base_mmr"])
        writer.writerow(["76561198899999901", "2000"])
        writer.writerow(["76561198899999902", "2500"])
        writer.writerow(["76561198899999903", "3000"])
    print(f"  Generated: {stubs_path}")
