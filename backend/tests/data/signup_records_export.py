"""Synthetic scope owned only by the sign-up records export browser tests."""

from typing import Final

from tests.data.models import TestOrganization, TestUser

SIGNUP_RECORDS_EXPORT_ORG: Final[TestOrganization] = TestOrganization(
    pk=62,
    name="Records Export Org",
    description="Isolated sign-up records export browser scenarios.",
    timezone="UTC",
)

SIGNUP_RECORDS_EXPORT_USERS: Final[tuple[TestUser, ...]] = tuple(
    TestUser(
        pk=9300 + index,
        username=f"records_export_{role}",
        nickname=f"Export {role.title()}",
        discord_id=str(930_000_000_000_000_000 + index),
        steam_id=310_009_300 + index,
    )
    for index, role in enumerate(
        ("staff", "admin", "member", "signer1", "signer2", "signer3")
    )
)

EXPORT_EVENT_NAMES: Final[dict[str, str]] = {
    "kept": "Export Kept Night",
    "cancelled": "Export Cancelled Night",
    "deleted": "Export Deleted Night",
}

EXPORT_EVENT_DAYS_AGO: Final[dict[str, int]] = {
    "kept": 10,
    "cancelled": 9,
    "deleted": 8,
}
