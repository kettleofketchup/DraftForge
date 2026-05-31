"""
Test User Configuration

Reference: docs/testing/auth/fixtures.md
If you update these users, also update the documentation!

This file defines the PKs and data for test users that are created
during database population and used by Playwright/Cypress tests.
"""

from tests.data.models import TestPositions, TestUser

# =============================================================================
# Site-Level Test Users (pk=1001-1031, for login fixtures)
# =============================================================================

# Admin user - site superuser
ADMIN_USER: TestUser = TestUser(
    pk=1001,
    username="kettleofketchup",
    discord_id="243497113906970625",
    steam_id_64=76561198012345678,
    is_staff=True,
    is_superuser=True,
)

# Staff user - site staff (not superuser)
STAFF_USER: TestUser = TestUser(
    pk=1002,
    username="hurk_",
    discord_id="702582402668560454",
    steam_id=None,
    is_staff=True,
    is_superuser=False,
)

# Regular user - basic access
REGULAR_USER: TestUser = TestUser(
    pk=1003,
    username="bucketoffish55",
    discord_id="198618246868500481",
    steam_id=None,
    is_staff=False,
    is_superuser=False,
)

# =============================================================================
# Claim Profile Test Users
# =============================================================================

# Claimable profile - manually added by org, NO Discord, HAS Steam ID
# This user CANNOT log in (no Discord ID)
CLAIMABLE_USER: TestUser = TestUser(
    pk=1010,
    username=None,  # No username - steamid is the identifier
    nickname="Claimable Profile",
    discord_id=None,
    steam_id_64=76561198099999999,
    mmr=4500,
)

# User Claimer - can log in, will claim the claimable profile
USER_CLAIMER: TestUser = TestUser(
    pk=1011,
    username="user_claimer",
    nickname="User Claimer",
    discord_id="100000000000000004",
    steam_id=None,  # No Steam ID - will claim a profile that has one
    is_staff=False,
    is_superuser=False,
)

# =============================================================================
# Organization Role Test Users
# =============================================================================

ORG_ADMIN_USER: TestUser = TestUser(
    pk=1020,
    username="org_admin_tester",
    nickname="Org Admin Tester",
    discord_id="100000000000000006",
    steam_id_64=76561198012345680,
    org_id=1,  # Admin of org 1
)

ORG_STAFF_USER: TestUser = TestUser(
    pk=1021,
    username="org_staff_tester",
    nickname="Org Staff Tester",
    discord_id="100000000000000007",
    steam_id_64=76561198012345681,
    org_id=1,  # Staff of org 1
)

# Plain org member — added to org 1's users but NOT to admins/staff. Tests
# need this distinct from REGULAR_USER (bucketoffish55) so the auth-matrix
# can separate the "member with no role" case from "unaffiliated user".
ORG_MEMBER_USER: TestUser = TestUser(
    pk=1022,
    username="org_member_tester",
    nickname="Org Member Tester",
    discord_id="100000000000000011",
    steam_id_64=76561198012345685,
    org_id=1,  # Member of org 1
)

# =============================================================================
# League Role Test Users
# =============================================================================

LEAGUE_ADMIN_USER: TestUser = TestUser(
    pk=1030,
    username="league_admin_tester",
    nickname="League Admin Tester",
    discord_id="100000000000000008",
    steam_id_64=76561198012345682,
    league_id=1,  # Admin of league 1
)

LEAGUE_STAFF_USER: TestUser = TestUser(
    pk=1031,
    username="league_staff_tester",
    nickname="League Staff Tester",
    discord_id="100000000000000009",
    steam_id_64=76561198012345683,
    league_id=1,  # Staff of league 1
)

EVENT_LEAGUE_STAFF_USER: TestUser = TestUser(
    pk=1032,
    username="event_league_staff_tester",
    nickname="Event League Staff Tester",
    discord_id="100000000000000010",
    steam_id_64=76561198012345684,
    league_id=7,  # Staff of Events Test League (league 7)
)

# =============================================================================
# Auth Matrix Role Test Users (pk=1090-1094)
# Dedicated to the role-context matrix at /tests/playwright/e2e/17-auth/.
# Scoped to AUTH_MATRIX_ORG (pk=8) and AUTH_MATRIX_LEAGUE (pk=9) so the
# matrix is fully isolated from DTX-using suites — neither side can flap
# the other by mutating org/league memberships.
# =============================================================================

AUTH_MATRIX_ORG_OWNER_USER: TestUser = TestUser(
    pk=1095,
    username="auth_matrix_org_owner",
    nickname="Auth Matrix Org Owner",
    discord_id="100000000000000095",
    steam_id_64=76561198012345695,
    org_id=8,  # Owner FK of Auth Matrix Test Org, NOT in admins M2M
)

AUTH_MATRIX_ORG_ADMIN_USER: TestUser = TestUser(
    pk=1090,
    username="auth_matrix_org_admin",
    nickname="Auth Matrix Org Admin",
    discord_id="100000000000000090",
    steam_id_64=76561198012345690,
    org_id=8,  # Admin of Auth Matrix Test Org
)

AUTH_MATRIX_ORG_STAFF_USER: TestUser = TestUser(
    pk=1091,
    username="auth_matrix_org_staff",
    nickname="Auth Matrix Org Staff",
    discord_id="100000000000000091",
    steam_id_64=76561198012345691,
    org_id=8,
)

AUTH_MATRIX_ORG_MEMBER_USER: TestUser = TestUser(
    pk=1092,
    username="auth_matrix_org_member",
    nickname="Auth Matrix Org Member",
    discord_id="100000000000000092",
    steam_id_64=76561198012345692,
    org_id=8,
)

AUTH_MATRIX_LEAGUE_ADMIN_USER: TestUser = TestUser(
    pk=1093,
    username="auth_matrix_league_admin",
    nickname="Auth Matrix League Admin",
    discord_id="100000000000000093",
    steam_id_64=76561198012345693,
    league_id=9,  # Admin of Auth Matrix League
)

AUTH_MATRIX_LEAGUE_STAFF_USER: TestUser = TestUser(
    pk=1094,
    username="auth_matrix_league_staff",
    nickname="Auth Matrix League Staff",
    discord_id="100000000000000094",
    steam_id_64=76561198012345694,
    league_id=9,
)

AUTH_MATRIX_USERS: list[TestUser] = [
    AUTH_MATRIX_ORG_OWNER_USER,
    AUTH_MATRIX_ORG_ADMIN_USER,
    AUTH_MATRIX_ORG_STAFF_USER,
    AUTH_MATRIX_ORG_MEMBER_USER,
    AUTH_MATRIX_LEAGUE_ADMIN_USER,
    AUTH_MATRIX_LEAGUE_STAFF_USER,
]

# =============================================================================
# Real Tournament 38 Users (pk=3000-3019, from production data)
# These are real users with Steam IDs for testing Steam league sync
# =============================================================================

TOURNAMENT_USERS: dict[str, TestUser] = {
    "just__khang": TestUser(
        pk=3000,
        username="just__khang",
        steam_id=237494518,
        mmr=4600,
        discord_id="279963469141377024",
        positions=TestPositions(
            carry=2, mid=3, offlane=1, soft_support=3, hard_support=5
        ),
    ),
    "clarexlauda": TestUser(
        pk=3001,
        username="clarexlauda",
        steam_id=150363706,
        mmr=2000,
        discord_id="990297849688391831",
        positions=TestPositions(
            carry=3, mid=0, offlane=0, soft_support=2, hard_support=1
        ),
    ),
    "heffdawgz": TestUser(
        pk=3002,
        username="heffdawgz",
        steam_id=84657820,
        mmr=5800,
        discord_id="214624382935367682",
        positions=TestPositions(
            carry=0, mid=1, offlane=0, soft_support=0, hard_support=0
        ),
    ),
    "pushingshots": TestUser(
        pk=3003,
        username="pushingshots",
        steam_id=104427945,
        mmr=2725,
        discord_id="403758532161437706",
        positions=TestPositions(
            carry=3, mid=5, offlane=0, soft_support=1, hard_support=2
        ),
    ),
    "anil98765": TestUser(
        pk=3004,
        username="anil98765",
        steam_id=104151469,
        mmr=2000,
        discord_id="435984979902595083",
        positions=TestPositions(
            carry=0, mid=0, offlane=0, soft_support=4, hard_support=5
        ),
    ),
    "tornope": TestUser(
        pk=3005,
        username="tornope",
        steam_id=174372053,
        mmr=3500,
        discord_id="376476737904836614",
        positions=TestPositions(
            carry=1, mid=0, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "nimstria1": TestUser(
        pk=3006,
        username="nimstria1",
        steam_id=171468462,
        mmr=500,
        discord_id="1303996935501381632",
        positions=TestPositions(
            carry=0, mid=0, offlane=0, soft_support=1, hard_support=1
        ),
    ),
    "creemy__": TestUser(
        pk=3007,
        username="creemy__",
        steam_id=114010086,
        mmr=4400,
        discord_id="359131134820483083",
        positions=TestPositions(
            carry=1, mid=0, offlane=2, soft_support=2, hard_support=2
        ),
    ),
    "ethan0688_": TestUser(
        pk=3008,
        username="ethan0688_",
        steam_id=875238678,
        mmr=6600,
        discord_id="1325607754177581066",
        positions=TestPositions(
            carry=2, mid=1, offlane=3, soft_support=4, hard_support=5
        ),
    ),
    "hassanzulfi": TestUser(
        pk=3009,
        username="hassanzulfi",
        steam_id=115198530,
        mmr=2700,
        discord_id="405344576480608257",
        positions=TestPositions(
            carry=0, mid=0, offlane=1, soft_support=2, hard_support=3
        ),
    ),
    "sir_t_rex": TestUser(
        pk=3010,
        username="sir_t_rex",
        steam_id=93840608,
        mmr=4500,
        discord_id="158695781216288768",
        positions=TestPositions(
            carry=1, mid=2, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "abaybay1392": TestUser(
        pk=3011,
        username="abaybay1392",
        steam_id=299870746,
        mmr=6700,
        discord_id="501861539033382933",
        positions=TestPositions(
            carry=1, mid=1, offlane=1, soft_support=2, hard_support=2
        ),
    ),
    "p0styp0sty": TestUser(
        pk=3012,
        username="p0styp0sty",
        steam_id=275837954,
        mmr=122,
        discord_id="556931015147520001",
        positions=TestPositions(
            carry=0, mid=0, offlane=0, soft_support=1, hard_support=2
        ),
    ),
    "reacher_z": TestUser(
        pk=3013,
        username="reacher_z",
        steam_id=84874902,
        mmr=400,
        discord_id="1164441465959743540",
        positions=TestPositions(
            carry=5, mid=4, offlane=3, soft_support=2, hard_support=1
        ),
    ),
    "vrm.mtl": TestUser(
        pk=3014,
        username="vrm.mtl",
        steam_id=151410512,
        mmr=6500,
        discord_id="764290890617192469",
        positions=TestPositions(
            carry=2, mid=1, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "gglive": TestUser(
        pk=3015,
        username="gglive",
        steam_id=1101709346,
        mmr=9000,
        discord_id="584468301988757504",
        positions=TestPositions(
            carry=0, mid=3, offlane=0, soft_support=2, hard_support=1
        ),
    ),
    "thekingauto": TestUser(
        pk=3016,
        username="thekingauto",
        steam_id=97505772,
        mmr=2920,
        discord_id="899703742012747797",
        positions=TestPositions(
            carry=1, mid=2, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "leafael.": TestUser(
        pk=3017,
        username="leafael.",
        steam_id=1098211999,
        mmr=4268,
        discord_id="740972649651634198",
        positions=TestPositions(
            carry=3, mid=0, offlane=0, soft_support=1, hard_support=3
        ),
    ),
    "benevolentgremlin": TestUser(
        pk=3018,
        username="benevolentgremlin",
        steam_id=150218787,
        mmr=6800,
        discord_id="186688726187900929",
        positions=TestPositions(
            carry=1, mid=0, offlane=4, soft_support=1, hard_support=4
        ),
    ),
    "bearthebear": TestUser(
        pk=3019,
        username="bearthebear",
        steam_id=240083333,
        mmr=2600,
        discord_id="251396038856802305",
        positions=TestPositions(
            carry=1, mid=4, offlane=4, soft_support=3, hard_support=4
        ),
    ),
}

# =============================================================================
# CSV Import Test Users (pk=2000-2004)
# These users exist in the DB but are NOT members of any org/tournament.
# CSV import tests use their Steam/Discord IDs to add them.
# =============================================================================

CSV_IMPORT_USERS: list[TestUser] = [
    TestUser(
        pk=2000,
        username="csv_steam_user",
        nickname="CSV Steam User",
        discord_id=None,
        steam_id_64=76561198800000001,
        mmr=4200,
    ),
    TestUser(
        pk=2001,
        username="csv_discord_user",
        nickname="CSV Discord User",
        discord_id="300000000000000001",
        steam_id=None,
        mmr=3800,
    ),
    TestUser(
        pk=2002,
        username="csv_both_ids",
        nickname="CSV Both IDs",
        discord_id="300000000000000002",
        steam_id_64=76561198800000003,
        mmr=5100,
    ),
    TestUser(
        pk=2003,
        username="csv_conflict_user",
        nickname="CSV Conflict User",
        discord_id="300000000000000099",
        steam_id_64=76561198800000004,
        mmr=4700,
    ),
    TestUser(
        pk=2004,
        username="csv_team_user",
        nickname="CSV Team User",
        discord_id=None,
        steam_id_64=76561198800000005,
        mmr=3500,
    ),
]

# =============================================================================
# User Edit Test Users (pk=2050-2058)
# Members of the User Edit Org / League / Tournament.
#
# Independent specs each own a dedicated user (so they can run in parallel
# without read-modify-write races on the same record). Sequential specs
# share alpha/bravo/charlie.
#
# pk   | username                  | owner
# -----|---------------------------|-----------------------------------
# 2050 | edit_user_alpha           | sequential specs (05, 07)
# 2051 | edit_user_bravo           | sequential specs (07 needs A+B)
# 2052 | edit_user_charlie         | sequential reserve
# 2053 | edit_user_org             | 01-org-edit
# 2054 | edit_user_tournament      | 02-tournament-edit
# 2055 | edit_user_league          | 03-league-edit
# 2056 | edit_user_mmr             | 04-org-mmr-edit
# 2057 | edit_user_positions       | 08-position-persistence
# 2058 | edit_user_cache           | 10-cache-merge
# =============================================================================

USER_EDIT_USERS: list[TestUser] = [
    TestUser(
        pk=2050,
        username="edit_user_alpha",
        nickname="Edit Alpha",
        discord_id="400000000000000001",
        steam_id_64=76561198900000001,
        mmr=3000,
    ),
    TestUser(
        pk=2051,
        username="edit_user_bravo",
        nickname="Edit Bravo",
        discord_id="400000000000000002",
        steam_id_64=76561198900000002,
        mmr=4500,
    ),
    TestUser(
        pk=2052,
        username="edit_user_charlie",
        nickname="Edit Charlie",
        discord_id="400000000000000003",
        steam_id_64=76561198900000003,
        mmr=5200,
    ),
    TestUser(
        pk=2053,
        username="edit_user_org",
        nickname="Edit Org",
        discord_id="400000000000000004",
        steam_id_64=76561198900000004,
        mmr=3100,
    ),
    TestUser(
        pk=2054,
        username="edit_user_tournament",
        nickname="Edit Tournament",
        discord_id="400000000000000005",
        steam_id_64=76561198900000005,
        mmr=3200,
    ),
    TestUser(
        pk=2055,
        username="edit_user_league",
        nickname="Edit League",
        discord_id="400000000000000006",
        steam_id_64=76561198900000006,
        mmr=3300,
    ),
    TestUser(
        pk=2056,
        username="edit_user_mmr",
        nickname="Edit MMR",
        discord_id="400000000000000007",
        steam_id_64=76561198900000007,
        mmr=3400,
    ),
    TestUser(
        pk=2057,
        username="edit_user_positions",
        nickname="Edit Positions",
        discord_id="400000000000000008",
        steam_id_64=76561198900000008,
        mmr=3500,
    ),
    TestUser(
        pk=2058,
        username="edit_user_cache",
        nickname="Edit Cache",
        discord_id="400000000000000009",
        steam_id_64=76561198900000009,
        mmr=3600,
    ),
]

# =============================================================================
# Shuffle Tie Test Users (pk=4000-4019)
# 4 captains + 16 available players for shuffle draft tie resolution tests.
# Captain 1 has 2000 MMR (picks first), Captains 2-4 have 3000 MMR (tie after pick).
# All available players have 2000 MMR.
# =============================================================================

SHUFFLE_TIE_CAPTAINS: list[TestUser] = [
    TestUser(
        pk=4000,
        username="tie_captain_alpha",
        nickname="Tie Captain Alpha",
        discord_id="500000000000000001",
        steam_id_64=76561199000000001,
        mmr=2000,
    ),
    TestUser(
        pk=4001,
        username="tie_captain_beta",
        nickname="Tie Captain Beta",
        discord_id="500000000000000002",
        steam_id_64=76561199000000002,
        mmr=3000,
    ),
    TestUser(
        pk=4002,
        username="tie_captain_gamma",
        nickname="Tie Captain Gamma",
        discord_id="500000000000000003",
        steam_id_64=76561199000000003,
        mmr=3000,
    ),
    TestUser(
        pk=4003,
        username="tie_captain_delta",
        nickname="Tie Captain Delta",
        discord_id="500000000000000004",
        steam_id_64=76561199000000004,
        mmr=3000,
    ),
]

SHUFFLE_TIE_PLAYERS: list[TestUser] = [
    TestUser(
        pk=4004 + i,
        username=f"tie_player_{i + 1:02d}",
        nickname=f"Tie Player {i + 1:02d}",
        discord_id=f"50000000000000{i + 5:04d}",
        steam_id_64=76561199000000005 + i,
        mmr=2000,
    )
    for i in range(16)
]

SHUFFLE_TIE_USERS: list[TestUser] = SHUFFLE_TIE_CAPTAINS + SHUFFLE_TIE_PLAYERS

# =============================================================================
# Events E2E test users (pk=5000-5020)
# =============================================================================

EVENT_ADMIN_USER: TestUser = TestUser(
    pk=5000,
    username="event_org_admin",
    nickname="EventAdmin",
    discord_id="880000000000000001",
    steam_id_64=76561198900100001,
    mmr=4500,
    org_id=7,  # Events Test Org
    league_id=7,  # Events Test League
    positions=TestPositions(),
)

EVENT_PLAYER_1: TestUser = TestUser(
    pk=5001,
    username="event_player_1",
    nickname="EventPlayer1",
    discord_id="880000000000000002",
    steam_id_64=76561198900100002,
    mmr=3500,
    positions=TestPositions(),
)

EVENT_PLAYER_2: TestUser = TestUser(
    pk=5002,
    username="event_player_2",
    nickname="EventPlayer2",
    discord_id="880000000000000003",
    steam_id_64=76561198900100003,
    mmr=3000,
    positions=TestPositions(),
)

EVENT_PLAYER_3: TestUser = TestUser(
    pk=5003,
    username="event_player_3",
    nickname="EventPlayer3",
    discord_id="880000000000000004",
    steam_id_64=76561198900100004,
    mmr=4000,
    positions=TestPositions(),
)

EVENT_PLAYER_4: TestUser = TestUser(
    pk=5004,
    username="event_player_4",
    nickname="EventPlayer4",
    discord_id="880000000000000005",
    steam_id_64=76561198000000004,
    positions=TestPositions(carry=5, mid=4, offlane=1, soft_support=1, hard_support=1),
)

EVENT_PLAYER_5: TestUser = TestUser(
    pk=5005,
    username="event_player_5",
    nickname="EventPlayer5",
    discord_id="880000000000000006",
    steam_id_64=76561198000000005,
    positions=TestPositions(carry=1, mid=1, offlane=2, soft_support=5, hard_support=4),
)

EVENT_PLAYER_6: TestUser = TestUser(
    pk=5006,
    username="event_player_6",
    nickname="EventPlayer6",
    discord_id="880000000000000007",
    steam_id_64=76561198000000006,
    positions=TestPositions(carry=2, mid=5, offlane=2, soft_support=1, hard_support=1),
)

EVENT_PLAYER_7: TestUser = TestUser(
    pk=5007,
    username="event_player_7",
    nickname="EventPlayer7",
    discord_id="880000000000000008",
    steam_id_64=76561198000000007,
    positions=TestPositions(carry=1, mid=1, offlane=5, soft_support=3, hard_support=2),
)

EVENT_PLAYER_8: TestUser = TestUser(
    pk=5008,
    username="event_player_8",
    nickname="EventPlayer8",
    discord_id="880000000000000009",
    steam_id_64=76561198000000008,
    positions=TestPositions(carry=1, mid=2, offlane=1, soft_support=4, hard_support=5),
)

EVENT_PLAYER_9: TestUser = TestUser(
    pk=5009,
    username="event_player_9",
    nickname="EventPlayer9",
    discord_id="880000000000000010",
    steam_id_64=76561198000000009,
    positions=TestPositions(carry=4, mid=3, offlane=2, soft_support=1, hard_support=1),
)

EVENT_PLAYER_10: TestUser = TestUser(
    pk=5010,
    username="event_player_10",
    nickname="EventPlayer10",
    discord_id="880000000000000011",
    steam_id_64=76561198000000010,
    positions=TestPositions(carry=1, mid=1, offlane=3, soft_support=5, hard_support=3),
)

EVENT_PLAYER_11: TestUser = TestUser(
    pk=5011,
    username="event_player_11",
    nickname="EventPlayer11",
    discord_id="880000000000000012",
    steam_id_64=76561198000000011,
    positions=TestPositions(carry=5, mid=2, offlane=3, soft_support=1, hard_support=1),
)

EVENT_PLAYER_12: TestUser = TestUser(
    pk=5012,
    username="event_player_12",
    nickname="EventPlayer12",
    discord_id="880000000000000013",
    steam_id_64=76561198000000012,
    positions=TestPositions(carry=1, mid=4, offlane=1, soft_support=2, hard_support=5),
)

EVENT_PLAYER_13: TestUser = TestUser(
    pk=5013,
    username="event_player_13",
    nickname="EventPlayer13",
    discord_id="880000000000000014",
    steam_id_64=76561198000000013,
    positions=TestPositions(carry=2, mid=1, offlane=5, soft_support=4, hard_support=1),
)

EVENT_PLAYER_14: TestUser = TestUser(
    pk=5014,
    username="event_player_14",
    nickname="EventPlayer14",
    discord_id="880000000000000015",
    steam_id_64=76561198000000014,
    positions=TestPositions(carry=1, mid=1, offlane=1, soft_support=3, hard_support=5),
)

EVENT_PLAYER_15: TestUser = TestUser(
    pk=5015,
    username="event_player_15",
    nickname="EventPlayer15",
    discord_id="880000000000000016",
    steam_id_64=76561198000000015,
    positions=TestPositions(carry=4, mid=5, offlane=3, soft_support=2, hard_support=1),
)

EVENT_PLAYER_16: TestUser = TestUser(
    pk=5016,
    username="event_player_16",
    nickname="EventPlayer16",
    discord_id="880000000000000017",
    steam_id_64=76561198000000016,
    positions=TestPositions(carry=1, mid=2, offlane=4, soft_support=5, hard_support=3),
)

EVENT_PLAYER_17: TestUser = TestUser(
    pk=5017,
    username="event_player_17",
    nickname="EventPlayer17",
    discord_id="880000000000000018",
    steam_id_64=76561198000000017,
    positions=TestPositions(carry=3, mid=1, offlane=1, soft_support=2, hard_support=5),
)

EVENT_PLAYER_18: TestUser = TestUser(
    pk=5018,
    username="event_player_18",
    nickname="EventPlayer18",
    discord_id="880000000000000019",
    steam_id_64=76561198000000018,
    positions=TestPositions(carry=5, mid=3, offlane=4, soft_support=1, hard_support=2),
)

EVENT_PLAYER_19: TestUser = TestUser(
    pk=5019,
    username="event_player_19",
    nickname="EventPlayer19",
    discord_id="880000000000000020",
    steam_id_64=76561198000000019,
    positions=TestPositions(carry=2, mid=1, offlane=2, soft_support=4, hard_support=5),
)

EVENT_PLAYER_20: TestUser = TestUser(
    pk=5020,
    username="event_player_20",
    nickname="EventPlayer20",
    discord_id="880000000000000021",
    steam_id_64=76561198000000020,
    positions=TestPositions(carry=1, mid=5, offlane=3, soft_support=1, hard_support=3),
)

EVENT_PLAYER_NO_PROFILE: TestUser = TestUser(
    pk=5099,
    username="event_player_no_profile",
    nickname="No-Profile Player",
    discord_id="880000000000099999",
    steam_id_64=76561198900199999,
    mmr=None,
    # All-zero priorities so the EventSignupModal's prefill chip doesn't
    # auto-collapse the position section for this user. Default
    # TestPositions() seeds every role at 3 ("If the team needs"), which
    # the modal interprets as "user has picked positions" and triggers
    # the prefilled-summary chip — masking the picker in the @cicd
    # "incomplete profile opens modal with all sections" spec.
    positions=TestPositions(
        carry=0,
        mid=0,
        offlane=0,
        soft_support=0,
        hard_support=0,
    ),
)

EVENTS_USERS: list[TestUser] = [
    EVENT_PLAYER_1,
    EVENT_PLAYER_2,
    EVENT_PLAYER_3,
    EVENT_PLAYER_4,
    EVENT_PLAYER_5,
    EVENT_PLAYER_6,
    EVENT_PLAYER_7,
    EVENT_PLAYER_8,
    EVENT_PLAYER_9,
    EVENT_PLAYER_10,
    EVENT_PLAYER_11,
    EVENT_PLAYER_12,
    EVENT_PLAYER_13,
    EVENT_PLAYER_14,
    EVENT_PLAYER_15,
    EVENT_PLAYER_16,
    EVENT_PLAYER_17,
    EVENT_PLAYER_18,
    EVENT_PLAYER_19,
    EVENT_PLAYER_20,
    EVENT_PLAYER_NO_PROFILE,  # Loop 2 ([:4]) skips this naturally — no PlayerDotaProfile created.
]

# =============================================================================
# Auth Test Users (for iteration)
# =============================================================================

AUTH_TEST_USERS: list[TestUser] = [
    ADMIN_USER,
    STAFF_USER,
    REGULAR_USER,
    CLAIMABLE_USER,
    USER_CLAIMER,
    ORG_ADMIN_USER,
    ORG_STAFF_USER,
    ORG_MEMBER_USER,
    LEAGUE_ADMIN_USER,
    LEAGUE_STAFF_USER,
    EVENT_LEAGUE_STAFF_USER,
    *AUTH_MATRIX_USERS,
]

# Legacy alias
ALL_TEST_USERS = AUTH_TEST_USERS
