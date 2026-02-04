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
