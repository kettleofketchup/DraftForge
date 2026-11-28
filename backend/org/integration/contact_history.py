"""Paginated current receipt history of one bound event, for ``promotion:read``.

Pages follow the stable receipt primary key under a cursor signed to the org,
event and limit. A reread from the start shows edited and retracted receipts
as they are now; this is not an incremental change feed.
"""

from __future__ import annotations

from typing import Any, Final

from django.core import signing

from common.strict_json import parse_canonical_id
from org.integration.bindings import get_event_binding
from org.integration.errors import invalid
from org.integration.receipts import format_timestamp
from org.models_promotion_sync import ExternalPromotionReceipt, ReceiptSource

SCHEMA_VERSION: Final = 1
MAX_LIMIT: Final = 100
CURSOR_SALT: Final = "org.integration.contact-history"


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return MAX_LIMIT
    limit = parse_canonical_id(raw)
    if limit is None or limit > MAX_LIMIT:
        raise invalid("limit", f"must be between 1 and {MAX_LIMIT}")
    return limit


def _after(cursor: str | None, *, org_id: int, event_id: int, limit: int) -> int:
    if cursor is None:
        return 0
    try:
        position = signing.loads(cursor, salt=CURSOR_SALT)
    except signing.BadSignature:
        raise invalid("cursor", "is not valid for this request") from None
    if (
        type(position) is not dict
        or position.get("o") != org_id
        or position.get("e") != event_id
        or position.get("l") != limit
        or type(position.get("p")) is not int
    ):
        raise invalid("cursor", "is not valid for this request")
    return position["p"]


def _item(receipt: ExternalPromotionReceipt) -> dict[str, Any]:
    return {
        "receipt_id": str(receipt.pk),
        "source_contact_id": str(receipt.source_contact_id),
        "event_id": str(receipt.event_id),
        "discord_id": receipt.discord_id,
        "contact_method": receipt.contact_method,
        "contact_reason": receipt.contact_reason,
        "recorded_at": format_timestamp(receipt.recorded_at),
        "retracted_at": (
            format_timestamp(receipt.retracted_at) if receipt.retracted_at else None
        ),
        "source_revision": receipt.source_revision,
        "point_status": receipt.point_status,
    }


def list_contact_history(
    *, org_id: int, event_id: int, cursor: str | None, limit: int
) -> dict[str, object]:
    get_event_binding(org_id, event_id)
    after = _after(cursor, org_id=org_id, event_id=event_id, limit=limit)
    rows = list(
        ExternalPromotionReceipt.objects.filter(
            organization_id=org_id,
            source=ReceiptSource.CONTACT_LOG,
            event_id=event_id,
            pk__gt=after,
        ).order_by("pk")[: limit + 1]
    )
    page = rows[:limit]
    return {
        "schema_version": SCHEMA_VERSION,
        "items": [_item(receipt) for receipt in page],
        "next_cursor": (
            signing.dumps(
                {"o": org_id, "e": event_id, "l": limit, "p": page[-1].pk},
                salt=CURSOR_SALT,
            )
            if len(rows) > limit
            else None
        ),
    }
