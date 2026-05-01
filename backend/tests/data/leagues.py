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

# CSV Import Test League - isolated from other test data
CSV_LEAGUE: TestLeague = TestLeague(
    pk=3,  # Expected PK after creation
    name="CSV Import League",
    steam_league_id=17931,
    description="Isolated league for CSV import E2E tests.",
    rules="CSV import test rules.",
    timezone="America/New_York",
    organization_names=["CSV Import Org"],
)

# Demo CSV League - for demo video recording (separate from CSV E2E tests)
DEMO_CSV_LEAGUE: TestLeague = TestLeague(
    pk=4,  # Expected PK after creation
    name="Demo CSV League",
    steam_league_id=17932,
    description="League for CSV import demo video recording.",
    rules="Demo CSV rules.",
    timezone="America/New_York",
    organization_names=["Demo CSV Org"],
)

# User Edit Test League - isolated from other test data
USER_EDIT_LEAGUE: TestLeague = TestLeague(
    pk=5,  # Expected PK after creation
    name="User Edit League",
    steam_league_id=17933,
    description="Isolated league for user edit E2E tests.",
    rules="User edit test rules.",
    timezone="America/New_York",
    organization_names=["User Edit Org"],
)

# Shuffle Tie Test League - isolated from other test data
SHUFFLE_TIE_LEAGUE: TestLeague = TestLeague(
    pk=6,  # Expected PK after creation
    name="Shuffle Tie League",
    steam_league_id=17934,
    description="Isolated league for shuffle draft tie resolution E2E tests.",
    rules="Shuffle tie test rules.",
    timezone="America/New_York",
    organization_names=["Shuffle Tie Org"],
)

# Events E2E tests
EVENTS_LEAGUE: TestLeague = TestLeague(
    pk=7,
    name="Events Test League",
    steam_league_id=17935,
    organization_names=["Events Test Org"],
)

EVENTS_LEAGUE_ALT: TestLeague = TestLeague(
    pk=8,
    name="Events Test League B",
    steam_league_id=17936,
    organization_names=["Events Test Org"],
)

# =============================================================================
# Constants for easy access
# =============================================================================

DTX_LEAGUE_NAME = DTX_LEAGUE.name
DTX_STEAM_LEAGUE_ID = DTX_LEAGUE.steam_league_id

TEST_LEAGUE_NAME = TEST_LEAGUE.name
TEST_STEAM_LEAGUE_ID = TEST_LEAGUE.steam_league_id

CSV_LEAGUE_NAME = CSV_LEAGUE.name
CSV_STEAM_LEAGUE_ID = CSV_LEAGUE.steam_league_id

DEMO_CSV_LEAGUE_NAME = DEMO_CSV_LEAGUE.name
DEMO_CSV_STEAM_LEAGUE_ID = DEMO_CSV_LEAGUE.steam_league_id

USER_EDIT_LEAGUE_NAME = USER_EDIT_LEAGUE.name
USER_EDIT_STEAM_LEAGUE_ID = USER_EDIT_LEAGUE.steam_league_id

SHUFFLE_TIE_LEAGUE_NAME = SHUFFLE_TIE_LEAGUE.name
SHUFFLE_TIE_STEAM_LEAGUE_ID = SHUFFLE_TIE_LEAGUE.steam_league_id

EVENTS_LEAGUE_NAME = EVENTS_LEAGUE.name
EVENTS_LEAGUE_STEAM_ID = EVENTS_LEAGUE.steam_league_id

EVENTS_LEAGUE_ALT_NAME = EVENTS_LEAGUE_ALT.name
EVENTS_LEAGUE_ALT_STEAM_ID = EVENTS_LEAGUE_ALT.steam_league_id

# =============================================================================
# All Leagues (for iteration)
# =============================================================================

ALL_LEAGUES: list[TestLeague] = [
    DTX_LEAGUE,
    TEST_LEAGUE,
    CSV_LEAGUE,
    DEMO_CSV_LEAGUE,
    USER_EDIT_LEAGUE,
    SHUFFLE_TIE_LEAGUE,
    EVENTS_LEAGUE,
    EVENTS_LEAGUE_ALT,
]
