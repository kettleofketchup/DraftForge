"""MMR sync API E2E test data.

Used by frontend/tests/playwright/e2e/19-org-features/13-mmr-sync-api.spec.ts.
Created by tests.populate.mmr_sync (populate, and again by every reset).

- Org 55 "MMR Sync Org": mmr_sync unlocked.
- Org 56 "MMR Sync Locked Org": mmr_sync locked.

Users (pk 8100-8199):

- 8100 owner/admin of org 55, 8101 staff of org 55, 8102 member of org 55,
  8103 member of org 55 with a Steam account (the sync target),
  8104 owner/admin of org 56.
"""

from typing import Final

from tests.data.models import TestOrganization, TestUser

MMR_SYNC_ORG: TestOrganization = TestOrganization(
    pk=55,
    name="MMR Sync Org",
    description="Isolated organization for the MMR sync API E2E tests.",
    timezone="America/New_York",
)
MMR_SYNC_LOCKED_ORG: TestOrganization = TestOrganization(
    pk=56,
    name="MMR Sync Locked Org",
    description="MMR sync API stays locked until a site admin unlocks it.",
    timezone="America/New_York",
)
MMR_SYNC_ORGS: Final[tuple[TestOrganization, ...]] = (
    MMR_SYNC_ORG,
    MMR_SYNC_LOCKED_ORG,
)
MMR_SYNC_UNLOCKED_PKS: Final[frozenset[int]] = frozenset({MMR_SYNC_ORG.pk})

MMR_SYNC_DISCORD_BASE: Final[int] = 810_000_000_000_000_000


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(MMR_SYNC_DISCORD_BASE + pk),
    )


MS_ADMIN = _user(8100, "ms_admin", "Sync Admin")
MS_STAFF = _user(8101, "ms_staff", "Sync Staff")
MS_MEMBER = _user(8102, "ms_member", "Sync Member")
MS_PLAYER = TestUser(
    pk=8103,
    username="ms_player",
    nickname="Sync Player",
    discord_id=str(MMR_SYNC_DISCORD_BASE + 8103),
    steam_id=810_103,
)
MS_LOCKED_ADMIN = _user(8104, "ms_locked_admin", "Sync Locked Admin")

# Dota 2 org MMR the reset puts back on MS_PLAYER.
MS_PLAYER_SEED_MMR: Final[int] = 3000

# Login roles for /api/tests/login-mmr-sync/<role>/.
MMR_SYNC_ROLE_USERS: Final[dict[str, TestUser]] = {
    "admin": MS_ADMIN,
    "staff": MS_STAFF,
    "member": MS_MEMBER,
    "player": MS_PLAYER,
    "locked_admin": MS_LOCKED_ADMIN,
}

# (org, owner, admins, staff, members)
MMR_SYNC_ROLES: Final[
    tuple[
        tuple[
            TestOrganization, TestUser, list[TestUser], list[TestUser], list[TestUser]
        ],
        ...,
    ]
] = (
    (
        MMR_SYNC_ORG,
        MS_ADMIN,
        [MS_ADMIN],
        [MS_STAFF],
        [MS_ADMIN, MS_STAFF, MS_MEMBER, MS_PLAYER],
    ),
    (
        MMR_SYNC_LOCKED_ORG,
        MS_LOCKED_ADMIN,
        [MS_LOCKED_ADMIN],
        [],
        [MS_LOCKED_ADMIN],
    ),
)
