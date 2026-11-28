"""Org API connections E2E test data.

Used by frontend/tests/playwright/e2e/org-features/org-api-connections.spec.ts.
Created by tests.populate.org_api_connections (populate, and again by every
reset).

- Org 57 "API Connections Org": mmr_sync and promotion unlocked.
- Org 58 "API Connections Second Org": mmr_sync unlocked; the first org's
  admin is also its admin, so the specs can switch orgs.

Users (pk 8300-8399):

- 8300 owner/admin of both orgs, 8301 second admin of org 57, 8302 staff of
  org 57, 8303 member of org 57.
- 8304 and 8305 are Steam-linked members of org 57 (8304 seeded at 3000 MMR,
  8305 with none); 8306 is a member without a Steam account.
- 8307 owner/admin of org 58.

The fake transport answers only the FAKE_ORIGINS below; their hosts use the
reserved .test domain, so no real service is ever named or reached.
"""

from typing import Final

from tests.data.models import TestOrganization, TestUser

API_CONNECTIONS_ORG: TestOrganization = TestOrganization(
    pk=57,
    name="API Connections Org",
    description="Isolated organization for the org API connections E2E tests.",
    timezone="America/New_York",
)
API_CONNECTIONS_SECOND_ORG: TestOrganization = TestOrganization(
    pk=58,
    name="API Connections Second Org",
    description="Second org for the API connections org-switch checks.",
    timezone="America/New_York",
)
API_CONNECTIONS_ORGS: Final[tuple[TestOrganization, ...]] = (
    API_CONNECTIONS_ORG,
    API_CONNECTIONS_SECOND_ORG,
)

API_CONNECTIONS_DISCORD_BASE: Final[int] = 830_000_000_000_000_000


def _user(
    pk: int, username: str, nickname: str, steam_id: int | None = None
) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(API_CONNECTIONS_DISCORD_BASE + pk),
        steam_id=steam_id,
    )


AC_ADMIN = _user(8300, "ac_admin", "Connections Admin")
AC_ADMIN_TWO = _user(8301, "ac_admin_two", "Connections Admin Two")
AC_STAFF = _user(8302, "ac_staff", "Connections Staff")
AC_MEMBER = _user(8303, "ac_member", "Connections Member")
AC_PLAYER_ONE = _user(8304, "ac_player_one", "Connections Player One", 830_304)
AC_PLAYER_TWO = _user(8305, "ac_player_two", "Connections Player Two", 830_305)
AC_NO_STEAM = _user(8306, "ac_no_steam", "Connections No Steam")
AC_SECOND_ADMIN = _user(8307, "ac_second_admin", "Connections Second Admin")

# Dota 2 org MMRs the reset puts back.
AC_SEED_MMRS: Final[dict[int, int]] = {AC_PLAYER_ONE.pk: 3000}

# Login roles for /api/tests/login-org-api-connections/<role>/.
API_CONNECTIONS_ROLE_USERS: Final[dict[str, TestUser]] = {
    "admin": AC_ADMIN,
    "admin_two": AC_ADMIN_TWO,
    "staff": AC_STAFF,
    "member": AC_MEMBER,
    "second_admin": AC_SECOND_ADMIN,
}
API_CONNECTIONS_USERS: Final[tuple[TestUser, ...]] = (
    AC_ADMIN,
    AC_ADMIN_TWO,
    AC_STAFF,
    AC_MEMBER,
    AC_PLAYER_ONE,
    AC_PLAYER_TWO,
    AC_NO_STEAM,
    AC_SECOND_ADMIN,
)

# (org, owner, admins, staff, members, unlocked features)
API_CONNECTIONS_ROLES: Final[
    tuple[
        tuple[
            TestOrganization,
            TestUser,
            list[TestUser],
            list[TestUser],
            list[TestUser],
            frozenset[str],
        ],
        ...,
    ]
] = (
    (
        API_CONNECTIONS_ORG,
        AC_ADMIN,
        [AC_ADMIN, AC_ADMIN_TWO],
        [AC_STAFF],
        [
            AC_ADMIN,
            AC_ADMIN_TWO,
            AC_STAFF,
            AC_MEMBER,
            AC_PLAYER_ONE,
            AC_PLAYER_TWO,
            AC_NO_STEAM,
        ],
        frozenset({"mmr_sync", "promotion"}),
    ),
    (
        API_CONNECTIONS_SECOND_ORG,
        AC_SECOND_ADMIN,
        [AC_SECOND_ADMIN, AC_ADMIN],
        [],
        [AC_SECOND_ADMIN, AC_ADMIN],
        frozenset({"mmr_sync"}),
    ),
)

# Synthetic destinations served by tests.helpers.org_api_connections_transport.
FAKE_ORIGIN: Final[str] = "https://ratings.connections.test"
FAKE_MOVED_ORIGIN: Final[str] = "https://ratings-moved.connections.test"
FAKE_ORIGINS: Final[tuple[str, ...]] = (FAKE_ORIGIN, FAKE_MOVED_ORIGIN)
# The one credential the fake accepts; anything else gets 401.
FAKE_GOOD_CREDENTIAL: Final[str] = "fixture-accepted-credential"
FAKE_BAD_CREDENTIAL: Final[str] = "fixture-rejected-credential"
FAKE_PULL_PATH: Final[str] = "/mmr"
# Steam account ID no member holds: reported unmatched, never added.
FAKE_UNKNOWN_STEAM_ID: Final[int] = 839_999
FAKE_PULL_ROWS: Final[tuple[dict[str, int], ...]] = (
    {"steam_id": 830_304, "mmr": 4100},
    {"steam_id": 830_305, "mmr": 2500},
    {"steam_id": FAKE_UNKNOWN_STEAM_ID, "mmr": 1000},
)

# Seeded disabled connection of the second org, with one finished pull run.
SEEDED_CONNECTION_NAME: Final[str] = "Seeded disabled connection"
