"""
Test Team Configuration

Pre-defined teams for test tournaments.
Teams reference users by username from tests/data/users.py.
"""

from tests.data.models import TestTeam

# =============================================================================
# Real Tournament 38 Teams
# These teams are based on production Tournament 38 data
# =============================================================================

GGLIVE_TEAM: TestTeam = TestTeam(
    name="gglive's Team",
    captain_username="gglive",
    member_usernames=["gglive", "anil98765", "hassanzulfi", "abaybay1392", "reacher_z"],
    draft_order=1,
    tournament_name="Real Tournament 38",
)

BENEVOLENTGREMLIN_TEAM: TestTeam = TestTeam(
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
    tournament_name="Real Tournament 38",
)

ETHAN_TEAM: TestTeam = TestTeam(
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
    tournament_name="Real Tournament 38",
)

VRM_MTL_TEAM: TestTeam = TestTeam(
    name="vrm.mtl's Team",
    captain_username="vrm.mtl",
    member_usernames=["vrm.mtl", "tornope", "nimstria1", "thekingauto", "leafael."],
    draft_order=4,
    tournament_name="Real Tournament 38",
)

# =============================================================================
# Real Tournament 38 Team List (in draft order)
# =============================================================================

REAL_TOURNAMENT_38_TEAMS: list[TestTeam] = [
    GGLIVE_TEAM,
    BENEVOLENTGREMLIN_TEAM,
    ETHAN_TEAM,
    VRM_MTL_TEAM,
]

# =============================================================================
# Demo Tournament Teams (for HeroDraft/Shuffle/Snake demos)
# =============================================================================

# HeroDraft uses Team A and Team B
HERODRAFT_TEAM_A: TestTeam = TestTeam(
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
)

HERODRAFT_TEAM_B: TestTeam = TestTeam(
    name="Team B",
    captain_username="vrm.mtl",
    member_usernames=["vrm.mtl", "tornope", "nimstria1", "thekingauto", "leafael."],
    draft_order=2,
)

HERODRAFT_TEAMS: list[TestTeam] = [HERODRAFT_TEAM_A, HERODRAFT_TEAM_B]

# =============================================================================
# All Teams (for iteration)
# =============================================================================

ALL_TEAMS: list[TestTeam] = [
    *REAL_TOURNAMENT_38_TEAMS,
    HERODRAFT_TEAM_A,
    HERODRAFT_TEAM_B,
]
