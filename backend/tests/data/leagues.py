"""
Test League Configuration

This file defines the leagues used for test data.
These are created by populate_organizations_and_leagues().
"""

from tests.data.models import TestLeague

# =============================================================================
# Main Leagues
# =============================================================================

DTX_LEAGUE: TestLeague = TestLeague(
    pk=1,  # Expected PK after creation
    name="DTX League",
    steam_league_id=17929,  # Default Steam league ID used throughout the codebase
    description="Main DTX League for in-house tournaments.",
    rules="Standard DTX tournament rules apply.",
    timezone="America/New_York",
    organization_names=["DTX"],
)

TEST_LEAGUE: TestLeague = TestLeague(
    pk=2,  # Expected PK after creation
    name="Test League",
    steam_league_id=17930,  # Different Steam league ID for testing
    description="Test league for Cypress E2E tests.",
    rules="Test rules.",
    timezone="America/New_York",
    organization_names=["Test Organization"],
)

# =============================================================================
# Constants for easy access
# =============================================================================

DTX_LEAGUE_NAME = DTX_LEAGUE.name
DTX_STEAM_LEAGUE_ID = DTX_LEAGUE.steam_league_id

TEST_LEAGUE_NAME = TEST_LEAGUE.name
TEST_STEAM_LEAGUE_ID = TEST_LEAGUE.steam_league_id

# =============================================================================
# All Leagues (for iteration)
# =============================================================================

ALL_LEAGUES: list[TestLeague] = [
    DTX_LEAGUE,
    TEST_LEAGUE,
]
