"""
Test Team Configuration

Pre-defined teams for test tournaments.
Teams reference users by TestUser objects from tests/data/users.py.
"""

from tests.data.models import TestTeam
from tests.data.users import TOURNAMENT_USERS

# =============================================================================
# Shorthand aliases for TOURNAMENT_USERS (for cleaner team definitions)
# =============================================================================

gglive = TOURNAMENT_USERS["gglive"]
anil98765 = TOURNAMENT_USERS["anil98765"]
hassanzulfi = TOURNAMENT_USERS["hassanzulfi"]
abaybay1392 = TOURNAMENT_USERS["abaybay1392"]
reacher_z = TOURNAMENT_USERS["reacher_z"]
benevolentgremlin = TOURNAMENT_USERS["benevolentgremlin"]
clarexlauda = TOURNAMENT_USERS["clarexlauda"]
creemy__ = TOURNAMENT_USERS["creemy__"]
sir_t_rex = TOURNAMENT_USERS["sir_t_rex"]
bearthebear = TOURNAMENT_USERS["bearthebear"]
ethan0688_ = TOURNAMENT_USERS["ethan0688_"]
just__khang = TOURNAMENT_USERS["just__khang"]
heffdawgz = TOURNAMENT_USERS["heffdawgz"]
pushingshots = TOURNAMENT_USERS["pushingshots"]
p0styp0sty = TOURNAMENT_USERS["p0styp0sty"]
vrm_mtl = TOURNAMENT_USERS["vrm.mtl"]
tornope = TOURNAMENT_USERS["tornope"]
nimstria1 = TOURNAMENT_USERS["nimstria1"]
thekingauto = TOURNAMENT_USERS["thekingauto"]
leafael = TOURNAMENT_USERS["leafael."]

# =============================================================================
# Real Tournament 38 Teams
# These teams are based on production Tournament 38 data
# =============================================================================

GGLIVE_TEAM: TestTeam = TestTeam(
    name="gglive's Team",
    captain=gglive,
    members=[gglive, anil98765, hassanzulfi, abaybay1392, reacher_z],
    draft_order=1,
    tournament_name="Real Tournament 38",
)

BENEVOLENTGREMLIN_TEAM: TestTeam = TestTeam(
    name="benevolentgremlin's Team",
    captain=benevolentgremlin,
    members=[benevolentgremlin, clarexlauda, creemy__, sir_t_rex, bearthebear],
    draft_order=2,
    tournament_name="Real Tournament 38",
)

ETHAN_TEAM: TestTeam = TestTeam(
    name="ethan0688_'s Team",
    captain=ethan0688_,
    members=[ethan0688_, just__khang, heffdawgz, pushingshots, p0styp0sty],
    draft_order=3,
    tournament_name="Real Tournament 38",
)

VRM_MTL_TEAM: TestTeam = TestTeam(
    name="vrm.mtl's Team",
    captain=vrm_mtl,
    members=[vrm_mtl, tornope, nimstria1, thekingauto, leafael],
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
    captain=ethan0688_,
    members=[ethan0688_, just__khang, heffdawgz, pushingshots, p0styp0sty],
    draft_order=1,
)

HERODRAFT_TEAM_B: TestTeam = TestTeam(
    name="Team B",
    captain=vrm_mtl,
    members=[vrm_mtl, tornope, nimstria1, thekingauto, leafael],
    draft_order=2,
)

HERODRAFT_TEAMS: list[TestTeam] = [HERODRAFT_TEAM_A, HERODRAFT_TEAM_B]

# =============================================================================
# Bracket Unset Winner Test Teams
# For testing the "unset winner" flow in bracket management
# =============================================================================

UNSET_ALPHA_TEAM: TestTeam = TestTeam(
    name="Unset Alpha",
    captain=gglive,
    members=[gglive, anil98765, hassanzulfi, abaybay1392, reacher_z],
    draft_order=1,
    tournament_name="bracket:unsetWinner Tournament",
)

UNSET_BETA_TEAM: TestTeam = TestTeam(
    name="Unset Beta",
    captain=benevolentgremlin,
    members=[benevolentgremlin, clarexlauda, creemy__, sir_t_rex, bearthebear],
    draft_order=2,
    tournament_name="bracket:unsetWinner Tournament",
)

UNSET_GAMMA_TEAM: TestTeam = TestTeam(
    name="Unset Gamma",
    captain=ethan0688_,
    members=[ethan0688_, just__khang, heffdawgz, pushingshots, p0styp0sty],
    draft_order=3,
    tournament_name="bracket:unsetWinner Tournament",
)

UNSET_DELTA_TEAM: TestTeam = TestTeam(
    name="Unset Delta",
    captain=vrm_mtl,
    members=[vrm_mtl, tornope, nimstria1, thekingauto, leafael],
    draft_order=4,
    tournament_name="bracket:unsetWinner Tournament",
)

BRACKET_UNSET_WINNER_TEAMS: list[TestTeam] = [
    UNSET_ALPHA_TEAM,
    UNSET_BETA_TEAM,
    UNSET_GAMMA_TEAM,
    UNSET_DELTA_TEAM,
]

# =============================================================================
# All Teams (for iteration)
# =============================================================================

ALL_TEAMS: list[TestTeam] = [
    *REAL_TOURNAMENT_38_TEAMS,
    HERODRAFT_TEAM_A,
    HERODRAFT_TEAM_B,
    *BRACKET_UNSET_WINNER_TEAMS,
]
