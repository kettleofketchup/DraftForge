"""Org locked features E2E test data: Contributions and Promotion.

Used by frontend/tests/playwright/e2e/19-org-features/.
populate_org_features_data creates it and reset_org_features_data puts it
back between specs (tests.populate.org_features).

- 40 "Features Test Org": both features unlocked, public member list.
- 41 "Locked Features Org": both features locked.
- 42 "Private Features Org": both features unlocked, `members_private`.

Users (pk 7300-7399):

- 7300 owner of orgs 40 and 42, 7301 admin of orgs 40 and 42,
  7302 staff of org 40, 7303 promoter of org 40, 7304 member of org 40,
  7305 outsider (no org), 7306 owner/admin of org 41,
  7307 member of org 42.
- 7310-7319 Discord-linked players of the past tournaments 260-263 in org 40.
"""

from typing import Final

from tests.data.models import TestLeague, TestOrganization, TestUser

FEATURES_ORG: TestOrganization = TestOrganization(
    pk=40,
    name="Features Test Org",
    description="Isolated organization for the locked features E2E tests.",
    timezone="America/New_York",
)
LOCKED_FEATURES_ORG: TestOrganization = TestOrganization(
    pk=41,
    name="Locked Features Org",
    description="Both locked features stay locked.",
    timezone="America/New_York",
)
PRIVATE_FEATURES_ORG: TestOrganization = TestOrganization(
    pk=42,
    name="Private Features Org",
    description="Both locked features unlocked, with a private member list.",
    timezone="America/New_York",
)

ORG_FEATURES_ORGS: Final[tuple[TestOrganization, ...]] = (
    FEATURES_ORG,
    LOCKED_FEATURES_ORG,
    PRIVATE_FEATURES_ORG,
)
ORG_FEATURES_UNLOCKED_PKS: Final[frozenset[int]] = frozenset(
    {FEATURES_ORG.pk, PRIVATE_FEATURES_ORG.pk}
)
ORG_FEATURES_PRIVATE_PKS: Final[frozenset[int]] = frozenset({PRIVATE_FEATURES_ORG.pk})
FEATURES_ORG_DISCORD_LINK: Final[str] = "https://discord.gg/features-test"

FEATURES_LEAGUE: TestLeague = TestLeague(
    pk=40,
    name="Features Test League",
    steam_league_id=17941,
    organization_names=[FEATURES_ORG.name],
)
LOCKED_FEATURES_LEAGUE: TestLeague = TestLeague(
    pk=41,
    name="Locked Features League",
    steam_league_id=17942,
    organization_names=[LOCKED_FEATURES_ORG.name],
)
PRIVATE_FEATURES_LEAGUE: TestLeague = TestLeague(
    pk=42,
    name="Private Features League",
    steam_league_id=17943,
    organization_names=[PRIVATE_FEATURES_ORG.name],
)

# (org, league) pairs in creation order.
ORG_FEATURES_ORG_LEAGUES: Final[tuple[tuple[TestOrganization, TestLeague], ...]] = (
    (FEATURES_ORG, FEATURES_LEAGUE),
    (LOCKED_FEATURES_ORG, LOCKED_FEATURES_LEAGUE),
    (PRIVATE_FEATURES_ORG, PRIVATE_FEATURES_LEAGUE),
)

ORG_FEATURES_DISCORD_BASE: Final[int] = 730_000_000_000_000_000


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(ORG_FEATURES_DISCORD_BASE + pk),
    )


OF_OWNER = _user(7300, "of_owner", "Features Owner")
OF_ADMIN = _user(7301, "of_admin", "Features Admin")
OF_STAFF = _user(7302, "of_staff", "Features Staff")
OF_PROMOTER = _user(7303, "of_promoter", "Features Promoter")
OF_MEMBER = _user(7304, "of_member", "Features Member")
OF_OUTSIDER = _user(7305, "of_outsider", "Features Outsider")
OF_LOCKED_ADMIN = _user(7306, "of_locked_admin", "Locked Admin")
OF_PRIVATE_MEMBER = _user(7307, "of_private_member", "Private Member")

# Login roles for /api/tests/login-org-features/<role>/.
ORG_FEATURES_ROLE_USERS: Final[dict[str, TestUser]] = {
    "owner": OF_OWNER,
    "admin": OF_ADMIN,
    "staff": OF_STAFF,
    "promoter": OF_PROMOTER,
    "member": OF_MEMBER,
    "outsider": OF_OUTSIDER,
    "locked_admin": OF_LOCKED_ADMIN,
    "private_member": OF_PRIVATE_MEMBER,
}

ORG_FEATURES_PLAYERS: Final[list[TestUser]] = [
    _user(pk, f"of_player_{pk - 7309}", f"Features Player {pk - 7309}")
    for pk in range(7310, 7320)
]

ORG_FEATURES_USERS: Final[list[TestUser]] = [
    *ORG_FEATURES_ROLE_USERS.values(),
    *ORG_FEATURES_PLAYERS,
]

# Org memberships (OrgUser rows) per org pk. Role holders sit in the M2Ms too.
ORG_FEATURES_MEMBERS: Final[dict[int, list[TestUser]]] = {
    FEATURES_ORG.pk: [
        OF_OWNER,
        OF_ADMIN,
        OF_STAFF,
        OF_PROMOTER,
        OF_MEMBER,
        *ORG_FEATURES_PLAYERS,
    ],
    LOCKED_FEATURES_ORG.pk: [OF_LOCKED_ADMIN, *ORG_FEATURES_PLAYERS[:3]],
    PRIVATE_FEATURES_ORG.pk: [
        OF_OWNER,
        OF_ADMIN,
        OF_PRIVATE_MEMBER,
        *ORG_FEATURES_PLAYERS[:4],
    ],
}

# (pk, name, days before now, players) — past tournaments in FEATURES_LEAGUE.
ORG_FEATURES_TOURNAMENTS: Final[list[tuple[int, str, int, list[TestUser]]]] = [
    (260, "Features Cup 1", 28, ORG_FEATURES_PLAYERS[0:6]),
    (261, "Features Cup 2", 21, ORG_FEATURES_PLAYERS[2:8]),
    (262, "Features Cup 3", 14, ORG_FEATURES_PLAYERS[4:10]),
    (
        263,
        "Features Cup 4",
        7,
        [*ORG_FEATURES_PLAYERS[0:2], *ORG_FEATURES_PLAYERS[6:10]],
    ),
]

ORG_FEATURES_UPCOMING_EVENT_NAME: Final[str] = "Features Upcoming Event"
ORG_FEATURES_UPCOMING2_EVENT_NAME: Final[str] = "Features Second Upcoming Event"
ORG_FEATURES_COMPLETED_EVENT_NAME: Final[str] = "Features Completed Event"

ORG_FEATURES_TEMPLATES: Final[list[tuple[str, str]]] = [
    (
        "First invite",
        "Hey {player}! {promoter} from {org} here.\n\n"
        "We're running **{event}** on {event_time} ({event_time_relative}).\n\n"
        "Details and sign-up: {event_link}",
    ),
    (
        "Reminder",
        "Hi {player}, a reminder that {event} starts {event_time_relative}. "
        "Sign up: {event_link}",
    ),
]
ORG_FEATURES_TEMPLATE_NAMES: Final[list[str]] = [n for n, _ in ORG_FEATURES_TEMPLATES]

# (org pk, user, points, reason) manual awards seeded by the reset.
ORG_FEATURES_MANUAL_AWARDS: Final[list[tuple[int, TestUser, int, str]]] = [
    (PRIVATE_FEATURES_ORG.pk, OF_PRIVATE_MEMBER, 3, "Seeded award"),
    (PRIVATE_FEATURES_ORG.pk, ORG_FEATURES_PLAYERS[0], 2, "Seeded award"),
]
