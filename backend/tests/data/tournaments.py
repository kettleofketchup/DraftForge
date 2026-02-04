"""
Test Tournament Configuration

Pre-defined tournaments for testing.
All teams are imported from tests/data/teams.py to avoid duplication.
"""

from tests.data.leagues import DTX_STEAM_LEAGUE_ID
from tests.data.models import TestTournament
from tests.data.teams import (
    BRACKET_UNSET_WINNER_TEAMS,
    HERODRAFT_TEAMS,
    REAL_TOURNAMENT_38_TEAMS,
)

# =============================================================================
# Bracket Test Tournaments
# Used for Steam match population and bracket game testing
# =============================================================================

COMPLETED_BRACKET_TOURNAMENT: TestTournament = TestTournament(
    name="Completed Bracket Test",
    tournament_type="double_elimination",
    state="past",
    steam_league_id=DTX_STEAM_LEAGUE_ID,
    league_name="DTX League",
    completed_game_count=6,  # All 6 bracket games completed
    match_id_base=9000000001,
)

PARTIAL_BRACKET_TOURNAMENT: TestTournament = TestTournament(
    name="Partial Bracket Test",
    tournament_type="double_elimination",
    state="past",
    steam_league_id=DTX_STEAM_LEAGUE_ID,
    league_name="DTX League",
    completed_game_count=2,  # 2 games completed, 4 pending
    match_id_base=9000000101,
)

PENDING_BRACKET_TOURNAMENT: TestTournament = TestTournament(
    name="Pending Bracket Test",
    tournament_type="double_elimination",
    state="past",
    steam_league_id=DTX_STEAM_LEAGUE_ID,
    league_name="DTX League",
    completed_game_count=0,  # All games pending
    match_id_base=9000000201,
)

# List of bracket test tournaments (in order for steam population)
BRACKET_TEST_TOURNAMENTS: list[TestTournament] = [
    COMPLETED_BRACKET_TOURNAMENT,
    PARTIAL_BRACKET_TOURNAMENT,
    PENDING_BRACKET_TOURNAMENT,
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
# All Tournaments (for iteration)
# =============================================================================

ALL_TOURNAMENTS: list[TestTournament] = [
    REAL_TOURNAMENT_38,
    DEMO_HERODRAFT_TOURNAMENT,
    BRACKET_UNSET_WINNER_TOURNAMENT,
]
