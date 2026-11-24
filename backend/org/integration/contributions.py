"""All-time contribution totals for every org member, in keyset pages.

The adaptor pulls these so SFG can show DraftForge contribution points.
Only the ``contribution`` track counts: leadership and conduct rows share
the ledger table and are left out. The sum is the one ``member_totals``
uses (every ``contribution`` row for the member), done in one grouped query
per page instead of a query per member.

Every ``OrgUser`` of the org is listed, ordered by its PK, whether or not
they were contacted, have MMR or appear on the leaderboard. A member with no
contribution rows has ``"0"``. A member without a canonical Discord ID
cannot be mapped to SFG, so it is ``unavailable`` with no points; it is
never reported as zero.

Each page is read live and carries its own ``observed_at``; there is no
org-wide snapshot. Points may change between pages. The cursor is bound to
the org and to a fingerprint of the membership and identities (OrgUser,
user and Discord ID tuples), not to points, so a member joining, leaving or
relinking Discord makes an in-flight read 409 ``mapping_changed``. A
database failure is 503 ``ledger_unavailable``, never an empty or zeroed
page.
"""

from __future__ import annotations

import hashlib
from typing import Any

from django.db import DatabaseError
from django.db.models import Sum
from django.utils import timezone

from common.strict_json import parse_canonical_id
from org.integration.cursors import decode_cursor, encode_cursor
from org.integration.errors import IntegrationError
from org.integration.parsers import format_id
from org.integration.receipts import canonical_json, format_timestamp
from org.models import Organization, OrgUser
from org.standing import ledger
from telemetry.logging import get_logger

log = get_logger(__name__)

RESOURCE = "contributions"
TRACK = "contribution"
PERIOD = "all_time"
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
_FINGERPRINT_SCHEMA = 1

_Member = tuple[int, int, str | None]


def format_points(value: int) -> str:
    """A signed int64 as a canonical decimal string; ValueError otherwise."""
    if type(value) is not int or not INT64_MIN <= value <= INT64_MAX:
        raise ValueError("points are not a signed int64")
    return str(value)


def _canonical_discord(value: str | None) -> str | None:
    return value if parse_canonical_id(value) is not None else None


def _membership(org: Organization) -> list[_Member]:
    """``(org_user_pk, user_pk, discord_id|None)`` for every member, by PK."""
    return [
        (pk, user_id, _canonical_discord(discord_id))
        for pk, user_id, discord_id in OrgUser.objects.nocache()
        .filter(organization=org)
        .order_by("pk")
        .values_list("pk", "user_id", "user__discordId")
    ]


def _fingerprint(members: list[_Member]) -> str:
    raw = canonical_json({"v": _FINGERPRINT_SCHEMA, "members": members})
    return hashlib.sha256(raw.encode()).hexdigest()


def _totals(org: Organization, org_user_pks: list[int]) -> dict[int, int]:
    """Contribution-track sums for these members, in one grouped query.

    Members with no rows are absent; the caller reports them as zero.
    """
    rows = (
        ledger.track_rows(TRACK)
        .filter(organization=org, org_user_id__in=org_user_pks)
        .values("org_user_id")
        .annotate(total=Sum("points"))
        .order_by()
        .values_list("org_user_id", "total")
    )
    return {pk: total or 0 for pk, total in rows}


def _cursor_after(key: list[Any]) -> int:
    if len(key) != 1 or type(key[0]) is not int or key[0] < 1:
        raise IntegrationError("invalid_cursor", 400)
    return key[0]


def _unavailable(org: Organization) -> IntegrationError:
    log.warning(
        "integration_ledger_unavailable",
        system="org",
        subsystem="integration",
        org_id=org.pk,
    )
    return IntegrationError("ledger_unavailable", 503)


def _wire(member: _Member, totals: dict[int, int]) -> dict[str, str | None]:
    pk, user_id, discord_id = member
    row: dict[str, str | None] = {
        "user_id": format_id(user_id),
        "org_user_id": format_id(pk),
        "discord_id": discord_id,
    }
    if discord_id is None:
        row.update(status="unavailable", reason="discord_mapping_missing")
    else:
        row.update(status="available", points=format_points(totals.get(pk, 0)))
    return row


def list_contribution_totals(
    org: Organization, *, limit: int, cursor: str | None
) -> dict[str, Any]:
    """One keyset page of members and their all-time contribution totals."""
    observed_at = timezone.now()
    try:
        members = _membership(org)
    except DatabaseError:
        raise _unavailable(org) from None
    fingerprint = _fingerprint(members)
    after = 0
    if cursor is not None:
        after = _cursor_after(
            decode_cursor(
                cursor, org_id=org.pk, resource=RESOURCE, fingerprint=fingerprint
            )
        )
    remaining = [m for m in members if m[0] > after]
    page = remaining[:limit]
    try:
        totals = _totals(org, [m[0] for m in page if m[2] is not None])
    except DatabaseError:
        raise _unavailable(org) from None
    next_cursor = None
    if len(remaining) > limit:
        next_cursor = encode_cursor(
            org_id=org.pk, resource=RESOURCE, key=[page[-1][0]], fingerprint=fingerprint
        )
    return {
        "source": "draftforge",
        "track": TRACK,
        "period": PERIOD,
        "observed_at": format_timestamp(observed_at),
        "members": [_wire(m, totals) for m in page],
        "next_cursor": next_cursor,
    }
