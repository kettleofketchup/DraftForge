"""Signup history E2E test data.

Used by frontend/tests/playwright/e2e/20-signup-history/. Created by
tests.populate.signup_history.populate_signup_history_data.

- Org 60 "Signup History Org" (no league).
- Users 9000-9006: 9000 org admin (staff), 9001-9005 members, 9006 a
  non-member outsider.
- "Signup History Event" (pk auto-assigned): its signups are made through the
  events services, so the signup ledger has real entries.
"""

from typing import Final

from tests.data.models import TestOrganization, TestUser

SIGNUP_HISTORY_ORG: TestOrganization = TestOrganization(
    pk=60,
    name="Signup History Org",
    description="Isolated organization for the signup history E2E tests.",
    timezone="America/New_York",
)

SIGNUP_HISTORY_EVENT_NAME: Final[str] = "Signup History Event"
SIGNUP_HISTORY_REASON: Final[str] = (
    "Added after the captain confirmed availability in the scheduling thread, "
    "so this player takes the next open place in line."
)

SIGNUP_HISTORY_DISCORD_BASE: Final[int] = 900_000_000_000_000_000
SIGNUP_HISTORY_STEAM_BASE: Final[int] = 309_000_000


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(SIGNUP_HISTORY_DISCORD_BASE + pk),
        steam_id=SIGNUP_HISTORY_STEAM_BASE + pk,
    )


SIGNUP_HISTORY_STAFF: TestUser = _user(9000, "hist_staff", "Hist Staff")
SIGNUP_HISTORY_WITHDRAWER: TestUser = _user(9001, "hist_withdrawer", "Hist Withdrawer")
SIGNUP_HISTORY_BUTTON: TestUser = _user(9002, "hist_button", "Hist Button")
SIGNUP_HISTORY_REACTION: TestUser = _user(9003, "hist_reaction", "Hist Reaction")
SIGNUP_HISTORY_STAFF_ADDED: TestUser = _user(
    9004, "hist_staff_added", "Hist Staff Added"
)
SIGNUP_HISTORY_LONG_NICK: TestUser = _user(
    9005, "hist_long_nick", "HistMemberWithAnExtremelyLongUnbrokenNickname"
)
SIGNUP_HISTORY_OUTSIDER: TestUser = _user(9006, "hist_outsider", "Hist Outsider")

SIGNUP_HISTORY_MEMBERS: Final[tuple[TestUser, ...]] = (
    SIGNUP_HISTORY_WITHDRAWER,
    SIGNUP_HISTORY_BUTTON,
    SIGNUP_HISTORY_REACTION,
    SIGNUP_HISTORY_STAFF_ADDED,
    SIGNUP_HISTORY_LONG_NICK,
)

SIGNUP_HISTORY_USERS: Final[tuple[TestUser, ...]] = (
    SIGNUP_HISTORY_STAFF,
    *SIGNUP_HISTORY_MEMBERS,
    SIGNUP_HISTORY_OUTSIDER,
)
