"""
Test User Configuration

Reference: docs/testing/auth/fixtures.md
If you update these users, also update the documentation!

This file defines the PKs and data for test users that are created
during database population and used by Playwright/Cypress tests.
"""

from tests.data.models import TestPositions, TestUser

# =============================================================================
# Site-Level Test Users (for login fixtures)
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

# =============================================================================
# Real Tournament 38 Users (from production data)
# These are real users with Steam IDs for testing Steam league sync
# =============================================================================

TOURNAMENT_USERS: dict[str, TestUser] = {
    "just__khang": TestUser(
        username="just__khang",
        steam_id=237494518,
        mmr=4600,
        discord_id="279963469141377024",
        positions=TestPositions(
            carry=2, mid=3, offlane=1, soft_support=3, hard_support=5
        ),
    ),
    "clarexlauda": TestUser(
        username="clarexlauda",
        steam_id=150363706,
        mmr=2000,
        discord_id="990297849688391831",
        positions=TestPositions(
            carry=3, mid=0, offlane=0, soft_support=2, hard_support=1
        ),
    ),
    "heffdawgz": TestUser(
        username="heffdawgz",
        steam_id=84657820,
        mmr=5800,
        discord_id="214624382935367682",
        positions=TestPositions(
            carry=0, mid=1, offlane=0, soft_support=0, hard_support=0
        ),
    ),
    "pushingshots": TestUser(
        username="pushingshots",
        steam_id=104427945,
        mmr=2725,
        discord_id="403758532161437706",
        positions=TestPositions(
            carry=3, mid=5, offlane=0, soft_support=1, hard_support=2
        ),
    ),
    "anil98765": TestUser(
        username="anil98765",
        steam_id=104151469,
        mmr=2000,
        discord_id="435984979902595083",
        positions=TestPositions(
            carry=0, mid=0, offlane=0, soft_support=4, hard_support=5
        ),
    ),
    "tornope": TestUser(
        username="tornope",
        steam_id=174372053,
        mmr=3500,
        discord_id="376476737904836614",
        positions=TestPositions(
            carry=1, mid=0, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "nimstria1": TestUser(
        username="nimstria1",
        steam_id=171468462,
        mmr=500,
        discord_id="1303996935501381632",
        positions=TestPositions(
            carry=0, mid=0, offlane=0, soft_support=1, hard_support=1
        ),
    ),
    "creemy__": TestUser(
        username="creemy__",
        steam_id=114010086,
        mmr=4400,
        discord_id="359131134820483083",
        positions=TestPositions(
            carry=1, mid=0, offlane=2, soft_support=2, hard_support=2
        ),
    ),
    "ethan0688_": TestUser(
        username="ethan0688_",
        steam_id=875238678,
        mmr=6600,
        discord_id="1325607754177581066",
        positions=TestPositions(
            carry=2, mid=1, offlane=3, soft_support=4, hard_support=5
        ),
    ),
    "hassanzulfi": TestUser(
        username="hassanzulfi",
        steam_id=115198530,
        mmr=2700,
        discord_id="405344576480608257",
        positions=TestPositions(
            carry=0, mid=0, offlane=1, soft_support=2, hard_support=3
        ),
    ),
    "sir_t_rex": TestUser(
        username="sir_t_rex",
        steam_id=93840608,
        mmr=4500,
        discord_id="158695781216288768",
        positions=TestPositions(
            carry=1, mid=2, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "abaybay1392": TestUser(
        username="abaybay1392",
        steam_id=299870746,
        mmr=6700,
        discord_id="501861539033382933",
        positions=TestPositions(
            carry=1, mid=1, offlane=1, soft_support=2, hard_support=2
        ),
    ),
    "p0styp0sty": TestUser(
        username="p0styp0sty",
        steam_id=275837954,
        mmr=122,
        discord_id="556931015147520001",
        positions=TestPositions(
            carry=0, mid=0, offlane=0, soft_support=1, hard_support=2
        ),
    ),
    "reacher_z": TestUser(
        username="reacher_z",
        steam_id=84874902,
        mmr=400,
        discord_id="1164441465959743540",
        positions=TestPositions(
            carry=5, mid=4, offlane=3, soft_support=2, hard_support=1
        ),
    ),
    "vrm.mtl": TestUser(
        username="vrm.mtl",
        steam_id=151410512,
        mmr=6500,
        discord_id="764290890617192469",
        positions=TestPositions(
            carry=2, mid=1, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "gglive": TestUser(
        username="gglive",
        steam_id=1101709346,
        mmr=9000,
        discord_id="584468301988757504",
        positions=TestPositions(
            carry=0, mid=3, offlane=0, soft_support=2, hard_support=1
        ),
    ),
    "thekingauto": TestUser(
        username="thekingauto",
        steam_id=97505772,
        mmr=2920,
        discord_id="899703742012747797",
        positions=TestPositions(
            carry=1, mid=2, offlane=3, soft_support=0, hard_support=0
        ),
    ),
    "leafael.": TestUser(
        username="leafael.",
        steam_id=1098211999,
        mmr=4268,
        discord_id="740972649651634198",
        positions=TestPositions(
            carry=3, mid=0, offlane=0, soft_support=1, hard_support=3
        ),
    ),
    "benevolentgremlin": TestUser(
        username="benevolentgremlin",
        steam_id=150218787,
        mmr=6800,
        discord_id="186688726187900929",
        positions=TestPositions(
            carry=1, mid=0, offlane=4, soft_support=1, hard_support=4
        ),
    ),
    "bearthebear": TestUser(
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
# CSV Import Test Users
# These users exist in the DB but are NOT members of any org/tournament.
# CSV import tests use their Steam/Discord IDs to add them.
# =============================================================================

CSV_IMPORT_USERS: list[TestUser] = [
    TestUser(
        pk=1040,
        username="csv_steam_user",
        nickname="CSV Steam User",
        discord_id=None,
        steam_id_64=76561198800000001,
        mmr=4200,
    ),
    TestUser(
        pk=1041,
        username="csv_discord_user",
        nickname="CSV Discord User",
        discord_id="300000000000000001",
        steam_id=None,
        mmr=3800,
    ),
    TestUser(
        pk=1042,
        username="csv_both_ids",
        nickname="CSV Both IDs",
        discord_id="300000000000000002",
        steam_id_64=76561198800000003,
        mmr=5100,
    ),
    TestUser(
        pk=1043,
        username="csv_conflict_user",
        nickname="CSV Conflict User",
        discord_id="300000000000000099",
        steam_id_64=76561198800000004,
        mmr=4700,
    ),
    TestUser(
        pk=1044,
        username="csv_team_user",
        nickname="CSV Team User",
        discord_id=None,
        steam_id_64=76561198800000005,
        mmr=3500,
    ),
]

# =============================================================================
# User Edit Test Users
# These users are members of the User Edit Org/League/Tournament.
# User edit E2E tests modify their fields (MMR, nickname, etc.)
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
]

# =============================================================================
# Shuffle Tie Test Users
# 4 captains + 16 available players for shuffle draft tie resolution tests.
# Captain 1 has 2000 MMR (picks first), Captains 2-4 have 3000 MMR (tie after pick).
# All available players have 2000 MMR.
# =============================================================================

SHUFFLE_TIE_CAPTAINS: list[TestUser] = [
    TestUser(
        pk=1060,
        username="tie_captain_alpha",
        nickname="Tie Captain Alpha",
        discord_id="500000000000000001",
        steam_id_64=76561199000000001,
        mmr=2000,
    ),
    TestUser(
        pk=1061,
        username="tie_captain_beta",
        nickname="Tie Captain Beta",
        discord_id="500000000000000002",
        steam_id_64=76561199000000002,
        mmr=3000,
    ),
    TestUser(
        pk=1062,
        username="tie_captain_gamma",
        nickname="Tie Captain Gamma",
        discord_id="500000000000000003",
        steam_id_64=76561199000000003,
        mmr=3000,
    ),
    TestUser(
        pk=1063,
        username="tie_captain_delta",
        nickname="Tie Captain Delta",
        discord_id="500000000000000004",
        steam_id_64=76561199000000004,
        mmr=3000,
    ),
]

SHUFFLE_TIE_PLAYERS: list[TestUser] = [
    TestUser(
        pk=1064 + i,
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
# Events E2E test users (pk=1080-1100)
# =============================================================================

EVENT_ADMIN_USER: TestUser = TestUser(
    pk=1080,
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
    pk=1081,
    username="event_player_1",
    nickname="EventPlayer1",
    discord_id="880000000000000002",
    steam_id_64=76561198900100002,
    mmr=3500,
    positions=TestPositions(),
)

EVENT_PLAYER_2: TestUser = TestUser(
    pk=1082,
    username="event_player_2",
    nickname="EventPlayer2",
    discord_id="880000000000000003",
    steam_id_64=76561198900100003,
    mmr=3000,
    positions=TestPositions(),
)

EVENT_PLAYER_3: TestUser = TestUser(
    pk=1083,
    username="event_player_3",
    nickname="EventPlayer3",
    discord_id="880000000000000004",
    steam_id_64=76561198900100004,
    mmr=4000,
    positions=TestPositions(),
)

EVENT_PLAYER_4: TestUser = TestUser(
    pk=1084,
    username="event_player_4",
    nickname="EventPlayer4",
    discord_id="880000000000000005",
    steam_id_64=76561198000000004,
    positions=TestPositions(carry=5, mid=4, offlane=1, soft_support=1, hard_support=1),
)

EVENT_PLAYER_5: TestUser = TestUser(
    pk=1085,
    username="event_player_5",
    nickname="EventPlayer5",
    discord_id="880000000000000006",
    steam_id_64=76561198000000005,
    positions=TestPositions(carry=1, mid=1, offlane=2, soft_support=5, hard_support=4),
)

EVENT_PLAYER_6: TestUser = TestUser(
    pk=1086,
    username="event_player_6",
    nickname="EventPlayer6",
    discord_id="880000000000000007",
    steam_id_64=76561198000000006,
    positions=TestPositions(carry=2, mid=5, offlane=2, soft_support=1, hard_support=1),
)

EVENT_PLAYER_7: TestUser = TestUser(
    pk=1087,
    username="event_player_7",
    nickname="EventPlayer7",
    discord_id="880000000000000008",
    steam_id_64=76561198000000007,
    positions=TestPositions(carry=1, mid=1, offlane=5, soft_support=3, hard_support=2),
)

EVENT_PLAYER_8: TestUser = TestUser(
    pk=1088,
    username="event_player_8",
    nickname="EventPlayer8",
    discord_id="880000000000000009",
    steam_id_64=76561198000000008,
    positions=TestPositions(carry=1, mid=2, offlane=1, soft_support=4, hard_support=5),
)

EVENT_PLAYER_9: TestUser = TestUser(
    pk=1089,
    username="event_player_9",
    nickname="EventPlayer9",
    discord_id="880000000000000010",
    steam_id_64=76561198000000009,
    positions=TestPositions(carry=4, mid=3, offlane=2, soft_support=1, hard_support=1),
)

EVENT_PLAYER_10: TestUser = TestUser(
    pk=1090,
    username="event_player_10",
    nickname="EventPlayer10",
    discord_id="880000000000000011",
    steam_id_64=76561198000000010,
    positions=TestPositions(carry=1, mid=1, offlane=3, soft_support=5, hard_support=3),
)

EVENT_PLAYER_11: TestUser = TestUser(
    pk=1091,
    username="event_player_11",
    nickname="EventPlayer11",
    discord_id="880000000000000012",
    steam_id_64=76561198000000011,
    positions=TestPositions(carry=5, mid=2, offlane=3, soft_support=1, hard_support=1),
)

EVENT_PLAYER_12: TestUser = TestUser(
    pk=1092,
    username="event_player_12",
    nickname="EventPlayer12",
    discord_id="880000000000000013",
    steam_id_64=76561198000000012,
    positions=TestPositions(carry=1, mid=4, offlane=1, soft_support=2, hard_support=5),
)

EVENT_PLAYER_13: TestUser = TestUser(
    pk=1093,
    username="event_player_13",
    nickname="EventPlayer13",
    discord_id="880000000000000014",
    steam_id_64=76561198000000013,
    positions=TestPositions(carry=2, mid=1, offlane=5, soft_support=4, hard_support=1),
)

EVENT_PLAYER_14: TestUser = TestUser(
    pk=1094,
    username="event_player_14",
    nickname="EventPlayer14",
    discord_id="880000000000000015",
    steam_id_64=76561198000000014,
    positions=TestPositions(carry=1, mid=1, offlane=1, soft_support=3, hard_support=5),
)

EVENT_PLAYER_15: TestUser = TestUser(
    pk=1095,
    username="event_player_15",
    nickname="EventPlayer15",
    discord_id="880000000000000016",
    steam_id_64=76561198000000015,
    positions=TestPositions(carry=4, mid=5, offlane=3, soft_support=2, hard_support=1),
)

EVENT_PLAYER_16: TestUser = TestUser(
    pk=1096,
    username="event_player_16",
    nickname="EventPlayer16",
    discord_id="880000000000000017",
    steam_id_64=76561198000000016,
    positions=TestPositions(carry=1, mid=2, offlane=4, soft_support=5, hard_support=3),
)

EVENT_PLAYER_17: TestUser = TestUser(
    pk=1097,
    username="event_player_17",
    nickname="EventPlayer17",
    discord_id="880000000000000018",
    steam_id_64=76561198000000017,
    positions=TestPositions(carry=3, mid=1, offlane=1, soft_support=2, hard_support=5),
)

EVENT_PLAYER_18: TestUser = TestUser(
    pk=1098,
    username="event_player_18",
    nickname="EventPlayer18",
    discord_id="880000000000000019",
    steam_id_64=76561198000000018,
    positions=TestPositions(carry=5, mid=3, offlane=4, soft_support=1, hard_support=2),
)

EVENT_PLAYER_19: TestUser = TestUser(
    pk=1099,
    username="event_player_19",
    nickname="EventPlayer19",
    discord_id="880000000000000020",
    steam_id_64=76561198000000019,
    positions=TestPositions(carry=2, mid=1, offlane=2, soft_support=4, hard_support=5),
)

EVENT_PLAYER_20: TestUser = TestUser(
    pk=1100,
    username="event_player_20",
    nickname="EventPlayer20",
    discord_id="880000000000000021",
    steam_id_64=76561198000000020,
    positions=TestPositions(carry=1, mid=5, offlane=3, soft_support=1, hard_support=3),
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
    LEAGUE_ADMIN_USER,
    LEAGUE_STAFF_USER,
]

# Legacy alias
ALL_TEST_USERS = AUTH_TEST_USERS
