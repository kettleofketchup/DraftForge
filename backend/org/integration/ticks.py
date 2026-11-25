"""Which promotion candidates an imported external contact ticks.

A non-quarantined receipt for the event and a Discord ID ticks the candidate
row with that Discord ID, unless the receipt is linked to a different
account than the row's. So a Discord-only guild row ticks before and after
the person gets an account, and a Discord ID that moved to another account
does not carry its old contacts across.

Kept apart from ``contacts`` (the import) so the promoter candidate code can
use it without importing the subject universe, which imports it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db.models import Exists, OuterRef, Q, QuerySet

from org.models_promotion_sync import AssociationState, ExternalPromotionReceipt


def suppressing_receipts(event_id: int) -> QuerySet[ExternalPromotionReceipt]:
    """Receipts that can tick a candidate of ``event_id``."""
    return ExternalPromotionReceipt.objects.filter(event_id=event_id).exclude(
        association_state=AssociationState.QUARANTINED
    )


def external_contact_exists(event_id: int) -> Exists:
    """``Exists`` for a ``CustomUser`` queryset: the row's user is ticked."""
    return Exists(
        suppressing_receipts(event_id)
        .filter(discord_id=OuterRef("discordId"))
        .filter(Q(user__isnull=True) | Q(user=OuterRef("pk")))
    )


def _contact(receipt: ExternalPromotionReceipt) -> dict[str, Any]:
    return {
        "source": receipt.source,
        "recorded_at": receipt.recorded_at,
        "delivery_verified": False,
        "can_undo": False,
    }


def external_contacts(
    event_id: int, keys: Iterable[tuple[str, int | None]]
) -> dict[tuple[str, int | None], dict[str, Any]]:
    """The latest external contact per ``(discord_id, user_id)`` row key."""
    wanted = {(d, u) for d, u in keys if d}
    if not wanted:
        return {}
    receipts = suppressing_receipts(event_id).filter(
        discord_id__in={d for d, _ in wanted}
    )
    by_discord: dict[str, list[ExternalPromotionReceipt]] = {}
    for receipt in receipts.order_by("-recorded_at", "-pk"):
        by_discord.setdefault(receipt.discord_id, []).append(receipt)
    found: dict[tuple[str, int | None], dict[str, Any]] = {}
    for discord_id, user_id in wanted:
        match = next(
            (
                r
                for r in by_discord.get(discord_id, [])
                if r.user_id is None or r.user_id == user_id
            ),
            None,
        )
        if match is not None:
            found[(discord_id, user_id)] = _contact(match)
    return found


def external_contact_for(
    event_id: int, discord_id: str, *, user_id: int | None
) -> dict[str, Any] | None:
    """The latest external contact ticking this row, or ``None``."""
    return external_contacts(event_id, [(discord_id, user_id)]).get(
        (discord_id, user_id)
    )
