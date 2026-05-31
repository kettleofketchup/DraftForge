"""
Org Delete test data — four distinct users on a dedicated org.

Used by frontend/tests/playwright/e2e/17-org-delete/ to verify the
permission matrix on the Danger Zone UI.
"""

from tests.data.models import TestOrganization, TestUser

ORG_DELETE_ORG: TestOrganization = TestOrganization(
    pk=10,
    name="Org Delete Test Org",
    description="Isolated organization for org-delete E2E permission-matrix tests.",
    timezone="America/New_York",
)

ORG_DELETE_OWNER: TestUser = TestUser(
    pk=6000,
    username="org_delete_owner",
    nickname="Org Delete Owner",
    discord_id="700000000000000001",
    steam_id_64=76561199100000001,
)

ORG_DELETE_ADMIN: TestUser = TestUser(
    pk=6001,
    username="org_delete_admin",
    nickname="Org Delete Admin",
    discord_id="700000000000000002",
    steam_id_64=76561199100000002,
)

ORG_DELETE_STAFF: TestUser = TestUser(
    pk=6002,
    username="org_delete_staff",
    nickname="Org Delete Staff",
    discord_id="700000000000000003",
    steam_id_64=76561199100000003,
)

ORG_DELETE_MEMBER: TestUser = TestUser(
    pk=6003,
    username="org_delete_member",
    nickname="Org Delete Member",
    discord_id="700000000000000004",
    steam_id_64=76561199100000004,
)
