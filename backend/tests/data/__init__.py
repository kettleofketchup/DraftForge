"""
Test Data Package

Centralized test data configuration using Pydantic models.

Usage:
    from tests.data import ADMIN_USER, DTX_ORG, DTX_LEAGUE
    from tests.data.models import TestUser, TestOrganization, TestLeague
    from tests.data.users import TOURNAMENT_USERS
    from tests.data.teams import REAL_TOURNAMENT_38_TEAMS
"""

# Leagues
from tests.data.leagues import (
    ALL_LEAGUES,
    DTX_LEAGUE,
    DTX_LEAGUE_NAME,
    DTX_STEAM_LEAGUE_ID,
    TEST_LEAGUE,
    TEST_LEAGUE_NAME,
    TEST_STEAM_LEAGUE_ID,
)

# Models
from tests.data.models import (
    TestLeague,
    TestOrganization,
    TestPositions,
    TestTeam,
    TestTournament,
    TestUser,
)

# Organizations
from tests.data.organizations import (
    ALL_ORGANIZATIONS,
    DTX_ORG,
    DTX_ORG_NAME,
    TEST_ORG,
    TEST_ORG_NAME,
)

# Teams
from tests.data.teams import (
    ALL_TEAMS,
    BENEVOLENTGREMLIN_TEAM,
    ETHAN_TEAM,
    GGLIVE_TEAM,
    HERODRAFT_TEAM_A,
    HERODRAFT_TEAM_B,
    HERODRAFT_TEAMS,
    REAL_TOURNAMENT_38_TEAMS,
    VRM_MTL_TEAM,
)

# Tournaments
from tests.data.tournaments import (
    ALL_TOURNAMENTS,
    DEMO_HERODRAFT_TOURNAMENT,
    REAL_TOURNAMENT_38,
)

# Users
from tests.data.users import (
    ADMIN_USER,
    ALL_TEST_USERS,
    AUTH_TEST_USERS,
    CLAIMABLE_USER,
    LEAGUE_ADMIN_USER,
    LEAGUE_STAFF_USER,
    ORG_ADMIN_USER,
    ORG_STAFF_USER,
    REGULAR_USER,
    STAFF_USER,
    TOURNAMENT_USERS,
    USER_CLAIMER,
)

__all__ = [
    # Models
    "TestUser",
    "TestPositions",
    "TestOrganization",
    "TestLeague",
    "TestTeam",
    "TestTournament",
    # Organizations
    "DTX_ORG",
    "TEST_ORG",
    "DTX_ORG_NAME",
    "TEST_ORG_NAME",
    "ALL_ORGANIZATIONS",
    # Leagues
    "DTX_LEAGUE",
    "TEST_LEAGUE",
    "DTX_LEAGUE_NAME",
    "TEST_LEAGUE_NAME",
    "DTX_STEAM_LEAGUE_ID",
    "TEST_STEAM_LEAGUE_ID",
    "ALL_LEAGUES",
    # Users
    "ADMIN_USER",
    "STAFF_USER",
    "REGULAR_USER",
    "CLAIMABLE_USER",
    "USER_CLAIMER",
    "ORG_ADMIN_USER",
    "ORG_STAFF_USER",
    "LEAGUE_ADMIN_USER",
    "LEAGUE_STAFF_USER",
    "TOURNAMENT_USERS",
    "AUTH_TEST_USERS",
    "ALL_TEST_USERS",
    # Teams
    "GGLIVE_TEAM",
    "BENEVOLENTGREMLIN_TEAM",
    "ETHAN_TEAM",
    "VRM_MTL_TEAM",
    "REAL_TOURNAMENT_38_TEAMS",
    "HERODRAFT_TEAM_A",
    "HERODRAFT_TEAM_B",
    "HERODRAFT_TEAMS",
    "ALL_TEAMS",
    # Tournaments
    "REAL_TOURNAMENT_38",
    "DEMO_HERODRAFT_TOURNAMENT",
    "ALL_TOURNAMENTS",
]
