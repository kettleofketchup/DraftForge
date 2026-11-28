"""Synthetic scope owned only by signup-record survival browser tests."""

from typing import Final

from tests.data.models import TestOrganization, TestUser

SIGNUP_RECORDS_ORG: Final[TestOrganization] = TestOrganization(
    pk=61,
    name="Signup Records Org",
    description="Isolated signup-record preservation browser scenarios.",
    timezone="UTC",
)

SIGNUP_RECORDS_USERS: Final[tuple[TestUser, ...]] = tuple(
    TestUser(
        pk=9200 + index,
        username=f"records_{role}",
        nickname=f"Records {role.title()}",
        discord_id=str(920_000_000_000_000_000 + index),
        steam_id=310_009_200 + index,
    )
    for index, role in enumerate(("admin", "staff", "member"))
)

SCENARIO_NAMES: Final[dict[str, str]] = {
    "cancel": "Records Cancellation Night",
    "delete": "Records Deletion Night",
    "registered": "Records Registered Occurrence",
    "empty": "Records Empty Occurrence",
}
SERIES_NAME: Final[str] = "Records Weekly Series"
