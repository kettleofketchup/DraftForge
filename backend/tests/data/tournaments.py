"""
Test Tournament Configuration

Pre-defined tournaments for testing.
All teams are imported from tests/data/teams.py to avoid duplication.

Tournament Types:
- TestTournament: Pre-defined teams with TestUser objects
- DynamicTournamentConfig: Dynamically created with mock users/teams
"""

from tests.data.leagues import (
    CSV_STEAM_LEAGUE_ID,
    DTX_STEAM_LEAGUE_ID,
    USER_EDIT_STEAM_LEAGUE_ID,
)
from tests.data.models import DynamicTournamentConfig, TestTournament
from tests.data.teams import (
    BRACKET_UNSET_WINNER_TEAMS,
    HERODRAFT_TEAMS,
    REAL_TOURNAMENT_38_TEAMS,
)

# =============================================================================
# Dynamic Tournament Configs
# These tournaments are created with generated mock users and teams.
# pk values are assigned sequentially for consistent database access.
# =============================================================================

# All 6 bracket games completed - used for bracket badges, match stats tests
COMPLETED_BRACKET_CONFIG = DynamicTournamentConfig(
    pk=1,
    name="Completed Bracket Test",
    user_count=20,
    team_count=4,
    tournament_type="double_elimination",
    league_name="DTX League",
    completed_game_count=6,  # All 6 bracket games completed
    match_id_base=9000000001,
)

# 2 games completed, 4 pending - used for partial bracket tests
PARTIAL_BRACKET_CONFIG = DynamicTournamentConfig(
    pk=2,
    name="Partial Bracket Test",
    user_count=20,
    team_count=4,
    tournament_type="double_elimination",
    league_name="DTX League",
    completed_game_count=2,  # 2 games completed, 4 pending
    match_id_base=9000000101,
)

# 0 games completed, all pending - used for pending bracket tests
PENDING_BRACKET_CONFIG = DynamicTournamentConfig(
    pk=3,
    name="Pending Bracket Test",
    user_count=20,
    team_count=4,
    tournament_type="double_elimination",
    league_name="DTX League",
    completed_game_count=0,  # All games pending
    match_id_base=9000000201,
)

# Used for captain draft and shuffle draft tests
DRAFT_TEST_CONFIG = DynamicTournamentConfig(
    pk=4,
    name="Draft Test",
    user_count=30,
    team_count=6,
    tournament_type="double_elimination",
    league_name="DTX League",
)

# Larger tournament for general testing
LARGE_TOURNAMENT_CONFIG = DynamicTournamentConfig(
    pk=5,
    name="Large Tournament Test",
    user_count=40,
    team_count=8,
    tournament_type="single_elimination",
    league_name="DTX League",
)

# Test League tournament - used for multi-org/league testing
TEST_LEAGUE_TOURNAMENT_CONFIG = DynamicTournamentConfig(
    pk=6,
    name="Test League Tournament",
    user_count=20,
    team_count=4,
    tournament_type="double_elimination",
    league_name="Test League",
    organization_pk=2,  # Test Organization
)

# Bracket test configs (for steam match population)
BRACKET_TEST_CONFIGS: list[DynamicTournamentConfig] = [
    COMPLETED_BRACKET_CONFIG,
    PARTIAL_BRACKET_CONFIG,
    PENDING_BRACKET_CONFIG,
]

# =============================================================================
# Real Tournament 38
# Based on production Tournament 38 data for testing Steam league sync
# =============================================================================

REAL_TOURNAMENT_38: TestTournament = TestTournament(
    name="Real Tournament 38",
    tournament_type="double_elimination",
    state="past",
    steam_league_id=DTX_STEAM_LEAGUE_ID,
    league_name="DTX League",
    date_played="2026-01-18",
    teams=REAL_TOURNAMENT_38_TEAMS,
)

# =============================================================================
# Demo Tournaments
# Used for demo video recording and UI testing
# =============================================================================

DEMO_HERODRAFT_TOURNAMENT: TestTournament = TestTournament(
    name="Demo HeroDraft Tournament",
    tournament_type="double_elimination",
    state="ongoing",
    steam_league_id=DTX_STEAM_LEAGUE_ID,
    league_name="DTX League",
    teams=HERODRAFT_TEAMS,
)

# =============================================================================
# Bracket Unset Winner Tournament
# Used for E2E testing the "unset winner" bracket management flow
# Creates a 4-team double elimination with ALL games PENDING (no completed games)
# =============================================================================

BRACKET_UNSET_WINNER_TOURNAMENT: TestTournament = TestTournament(
    name="bracket:unsetWinner Tournament",
    tournament_type="double_elimination",
    state="in_progress",
    steam_league_id=DTX_STEAM_LEAGUE_ID,
    league_name="DTX League",
    teams=BRACKET_UNSET_WINNER_TEAMS,
)

# =============================================================================
# CSV Import Tournament
# Isolated tournament for CSV import E2E tests.
# Starts empty (no users/teams) - CSV import adds them.
# =============================================================================

CSV_IMPORT_TOURNAMENT: TestTournament = TestTournament(
    name="CSV Import Tournament",
    tournament_type="double_elimination",
    state="in_progress",
    steam_league_id=CSV_STEAM_LEAGUE_ID,
    league_name="CSV Import League",
    organization_pk=3,  # CSV Import Org
    teams=[],  # Empty - CSV import adds users
)

# =============================================================================
# User Edit Tournament
# Isolated tournament for user edit E2E tests.
# Has 3 pre-added users for editing tests.
# =============================================================================

USER_EDIT_TOURNAMENT: TestTournament = TestTournament(
    name="User Edit Tournament",
    tournament_type="double_elimination",
    state="in_progress",
    steam_league_id=USER_EDIT_STEAM_LEAGUE_ID,
    league_name="User Edit League",
    organization_pk=5,  # User Edit Org
    teams=[],  # No teams needed - just users
)
