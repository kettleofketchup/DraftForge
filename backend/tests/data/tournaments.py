"""
Test Tournament Configuration

Pre-defined tournaments for testing.
"""

from tests.data.leagues import DTX_STEAM_LEAGUE_ID
from tests.data.models import TestTeam, TestTournament

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
    teams=[
        TestTeam(
            name="gglive's Team",
            captain_username="gglive",
            member_usernames=[
                "gglive",
                "anil98765",
                "hassanzulfi",
                "abaybay1392",
                "reacher_z",
            ],
            draft_order=1,
        ),
        TestTeam(
            name="benevolentgremlin's Team",
            captain_username="benevolentgremlin",
            member_usernames=[
                "benevolentgremlin",
                "clarexlauda",
                "creemy__",
                "sir_t_rex",
                "bearthebear",
            ],
            draft_order=2,
        ),
        TestTeam(
            name="ethan0688_'s Team",
            captain_username="ethan0688_",
            member_usernames=[
                "ethan0688_",
                "just__khang",
                "heffdawgz",
                "pushingshots",
                "p0styp0sty",
            ],
            draft_order=3,
        ),
        TestTeam(
            name="vrm.mtl's Team",
            captain_username="vrm.mtl",
            member_usernames=[
                "vrm.mtl",
                "tornope",
                "nimstria1",
                "thekingauto",
                "leafael.",
            ],
            draft_order=4,
        ),
    ],
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
    teams=[
        TestTeam(
            name="Team A",
            captain_username="ethan0688_",
            member_usernames=[
                "ethan0688_",
                "just__khang",
                "heffdawgz",
                "pushingshots",
                "p0styp0sty",
            ],
            draft_order=1,
        ),
        TestTeam(
            name="Team B",
            captain_username="vrm.mtl",
            member_usernames=[
                "vrm.mtl",
                "tornope",
                "nimstria1",
                "thekingauto",
                "leafael.",
            ],
            draft_order=2,
        ),
    ],
)

# =============================================================================
# All Tournaments (for iteration)
# =============================================================================

ALL_TOURNAMENTS: list[TestTournament] = [
    REAL_TOURNAMENT_38,
    DEMO_HERODRAFT_TOURNAMENT,
]
