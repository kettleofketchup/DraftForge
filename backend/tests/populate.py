"""
Test Database Population - Backwards Compatibility Module

This file re-exports everything from the tests.populate package for
backwards compatibility. New code should import directly from
tests.populate instead.

Example:
    # Old way (still works)
    from tests.populate import populate_all

    # New way (preferred)
    from tests.populate import populate_all
"""

# Re-export everything from the populate package
from tests.populate import (  # Main entry point; Population functions; Utilities; Constants
    DTX_LEAGUE_NAME,
    DTX_ORG_NAME,
    DTX_STEAM_LEAGUE_ID,
    MOCK_USERNAMES,
    REAL_TOURNAMENT_USERS,
    TEST_LEAGUE_NAME,
    TEST_ORG_NAME,
    TEST_STEAM_LEAGUE_ID,
    TOURNAMENT_USERS,
    create_user,
    ensure_league_user,
    ensure_org_user,
    flush_redis_cache,
    generate_mock_discord_members,
    get_or_create_demo_user,
    populate_all,
    populate_bracket_linking_scenario,
    populate_bracket_unset_winner_tournament,
    populate_demo_tournaments,
    populate_organizations_and_leagues,
    populate_real_tournament_38,
    populate_steam_matches,
    populate_test_auth_users,
    populate_tournaments,
    populate_users,
    test_user_to_dict,
)

# Backwards compatibility aliases with underscore prefix
_ensure_org_user = ensure_org_user
_ensure_league_user = ensure_league_user
_flush_redis_cache = flush_redis_cache
_test_user_to_dict = test_user_to_dict
_get_or_create_demo_user = get_or_create_demo_user
_fetch_discord_avatars_for_users = (
    None  # Deprecated, use fetch_discord_avatars_for_users
)

# Re-export for backwards compatibility with `from tests.populate import *`
__all__ = [
    "populate_all",
    "populate_organizations_and_leagues",
    "populate_users",
    "populate_test_auth_users",
    "populate_tournaments",
    "populate_real_tournament_38",
    "populate_steam_matches",
    "populate_bracket_linking_scenario",
    "populate_bracket_unset_winner_tournament",
    "populate_demo_tournaments",
    "create_user",
    "generate_mock_discord_members",
    "ensure_org_user",
    "ensure_league_user",
    "flush_redis_cache",
    "test_user_to_dict",
    "get_or_create_demo_user",
    "REAL_TOURNAMENT_USERS",
    "DTX_ORG_NAME",
    "DTX_LEAGUE_NAME",
    "DTX_STEAM_LEAGUE_ID",
    "TEST_ORG_NAME",
    "TEST_LEAGUE_NAME",
    "TEST_STEAM_LEAGUE_ID",
    "TOURNAMENT_USERS",
    "MOCK_USERNAMES",
]
