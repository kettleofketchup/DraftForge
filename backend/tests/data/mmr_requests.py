"""MMR update request E2E test data.

Used by frontend/tests/playwright/e2e/11-org-mmr/05-mmr-update-requests.spec.ts.
Created by tests.populate.mmr_requests.populate_mmr_requests_data.

- Org / league 60 "MMR Requests Org" / "MMR Requests League" (steam league 17945).
- Members 8200-8202: Dota org MMR 4200 (unverified) and a league row at 4200.
  - 8200: requests an update that org staff approve.
  - 8201: requests an update that staff reject; also the league request.
  - 8202: staff set an official MMR from the edit modal.
- 8203: org staff. 8204: league staff (not an org member). 8205: outsider.
"""

from typing import Final

from tests.data.models import TestLeague, TestOrganization, TestUser

MMR_REQ_ORG_PK: Final[int] = 60
MMR_REQ_LEAGUE_PK: Final[int] = 60
MEMBER_APPROVE_PK: Final[int] = 8200
MEMBER_REJECT_PK: Final[int] = 8201
MEMBER_STAFFSET_PK: Final[int] = 8202
ORG_STAFF_PK: Final[int] = 8203
LEAGUE_STAFF_PK: Final[int] = 8204
OUTSIDER_PK: Final[int] = 8205

MMR_REQ_BASE_MMR: Final[int] = 4200

MMR_REQ_ORG: TestOrganization = TestOrganization(
    pk=MMR_REQ_ORG_PK,
    name="MMR Requests Org",
    description="Isolated organization for the MMR update request E2E tests.",
    timezone="America/New_York",
)

MMR_REQ_LEAGUE: TestLeague = TestLeague(
    pk=MMR_REQ_LEAGUE_PK,
    name="MMR Requests League",
    steam_league_id=17945,
    organization_names=[MMR_REQ_ORG.name],
)

MMR_REQ_DISCORD_BASE: Final[int] = 820_000_000_000_000_000


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(MMR_REQ_DISCORD_BASE + pk),
    )


MMR_REQ_MEMBER_APPROVE: TestUser = _user(
    MEMBER_APPROVE_PK, "mmrreq_approve", "MMR Req Approve"
)
MMR_REQ_MEMBER_REJECT: TestUser = _user(
    MEMBER_REJECT_PK, "mmrreq_reject", "MMR Req Reject"
)
MMR_REQ_MEMBER_STAFFSET: TestUser = _user(
    MEMBER_STAFFSET_PK, "mmrreq_staffset", "MMR Req Staffset"
)
MMR_REQ_ORG_STAFF: TestUser = _user(ORG_STAFF_PK, "mmrreq_org_staff", "MMR Req Staff")
MMR_REQ_LEAGUE_STAFF: TestUser = _user(
    LEAGUE_STAFF_PK, "mmrreq_league_staff", "MMR Req League Staff"
)
MMR_REQ_OUTSIDER: TestUser = _user(OUTSIDER_PK, "mmrreq_outsider", "MMR Req Outsider")

MMR_REQ_MEMBERS: Final[tuple[TestUser, ...]] = (
    MMR_REQ_MEMBER_APPROVE,
    MMR_REQ_MEMBER_REJECT,
    MMR_REQ_MEMBER_STAFFSET,
)

MMR_REQ_USERS: Final[tuple[TestUser, ...]] = (
    *MMR_REQ_MEMBERS,
    MMR_REQ_ORG_STAFF,
    MMR_REQ_LEAGUE_STAFF,
    MMR_REQ_OUTSIDER,
)
