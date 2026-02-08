"""
Test Database Population Package

This package contains modular functions for populating the test database.
Each module focuses on a specific domain:
- organizations: Organization and league setup
- users: User population (mock and real)
- tournaments: Tournament population
- steam: Steam match data population
- bracket: Bracket-specific test scenarios
- demo: Demo tournaments for video recording

Usage:
    from tests.populate import populate_all
    populate_all(force=True)

Or import specific functions:
    from tests.populate import populate_users, populate_tournaments
"""

# Re-export commonly used functions for backwards compatibility
from tests.populate.bracket import (
    populate_bracket_linking_scenario,
    populate_bracket_unset_winner_tournament,
)

# Re-export constants
from tests.populate.constants import (
    DTX_LEAGUE_NAME,
    DTX_ORG_NAME,
    DTX_STEAM_LEAGUE_ID,
    MOCK_USERNAMES,
    TEST_LEAGUE_NAME,
    TEST_ORG_NAME,
    TEST_STEAM_LEAGUE_ID,
    TOURNAMENT_USERS,
)
from tests.populate.csv_import import populate_csv_import_data
from tests.populate.demo import populate_demo_tournaments
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.steam import populate_steam_matches
from tests.populate.tournaments import populate_real_tournament_38, populate_tournaments
from tests.populate.users import populate_test_auth_users, populate_users

# Re-export utilities that may be used directly
from tests.populate.utils import (
    REAL_TOURNAMENT_USERS,
    create_user,
    ensure_league_user,
    ensure_org_user,
    flush_redis_cache,
    generate_mock_discord_members,
    get_or_create_demo_user,
    test_user_to_dict,
)


def populate_all(force=False):
    """
    Run all population functions in the correct order.

    This is the main entry point for populating the test database.
    Functions are run in dependency order:
    1. Organizations and leagues (required by all others)
    2. Users (required by tournaments)
    3. Test auth users (for Playwright/Cypress tests)
    4. Real Tournament 38 (for Steam league sync testing)
    5. Test tournaments (various scenarios)
    6. Steam matches (bracket game data)
    7. Bracket linking scenario (specific test case)
    8. Bracket unset winner tournament (E2E test)
    9. Demo tournaments (for video recording)

    Args:
        force: If True, recreate data even if it exists
    """
    populate_organizations_and_leagues(force)
    populate_users(force)
    populate_test_auth_users(force)
    populate_real_tournament_38(force)
    populate_tournaments(force)
    populate_steam_matches(force)
    populate_bracket_linking_scenario(force)
    populate_bracket_unset_winner_tournament(force)
    populate_csv_import_data(force)
    populate_demo_tournaments(force)


__all__ = [
    # Main entry point
    "populate_all",
    # Population functions
    "populate_organizations_and_leagues",
    "populate_users",
    "populate_test_auth_users",
    "populate_tournaments",
    "populate_real_tournament_38",
    "populate_steam_matches",
    "populate_bracket_linking_scenario",
    "populate_bracket_unset_winner_tournament",
    "populate_csv_import_data",
    "populate_demo_tournaments",
    # Utilities
    "create_user",
    "generate_mock_discord_members",
    "ensure_org_user",
    "ensure_league_user",
    "flush_redis_cache",
    "test_user_to_dict",
    "get_or_create_demo_user",
    "REAL_TOURNAMENT_USERS",
    # Constants
    "DTX_ORG_NAME",
    "DTX_LEAGUE_NAME",
    "DTX_STEAM_LEAGUE_ID",
    "TEST_ORG_NAME",
    "TEST_LEAGUE_NAME",
    "TEST_STEAM_LEAGUE_ID",
    "TOURNAMENT_USERS",
    "MOCK_USERNAMES",
]
