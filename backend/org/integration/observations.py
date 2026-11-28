"""Range-aware scan ordering, including source IDs never stored as receipts.

All reads/writes run under the importing organization's transaction lock.
Only successfully committed coverage is retained; skipped IDs stay holes.
"""

from __future__ import annotations

from datetime import datetime
from heapq import heappop, heappush
from typing import TYPE_CHECKING

from org.models_promotion_sync import PromotionImportObservation, ReceiptSource

if TYPE_CHECKING:
    from org.integration.contacts import ImportBatch

SpanKey = tuple[datetime, int | None]


def newer_ranges(org_id: int, batch: ImportBatch) -> list[tuple[int, int]]:
    if batch.range_through is None:
        return []
    return list(
        PromotionImportObservation.objects.filter(
            organization_id=org_id,
            source=ReceiptSource.CONTACT_LOG,
            observed_at__gt=batch.scan_started_at,
            after__lt=batch.range_through,
            through__gt=batch.range_after,
        ).values_list("after", "through")
    )


def covered(source_id: int, ranges: list[tuple[int, int]]) -> bool:
    return any(after < source_id <= through for after, through in ranges)


def _order(key: SpanKey) -> tuple[datetime, int]:
    return key[0], -1 if key[1] is None else key[1]


def record_ranges(
    org_id: int, batch: ImportBatch, *, connection_id: int | None = None
) -> None:
    if batch.range_through is None:
        return
    stored = PromotionImportObservation.objects.filter(
        organization_id=org_id, source=ReceiptSource.CONTACT_LOG
    )
    spans: list[tuple[int, int, SpanKey]] = [
        (after, through, (observed, source))
        for after, through, observed, source in stored.values_list(
            "after", "through", "observed_at", "connection_id"
        )
    ]
    current: SpanKey = (batch.scan_started_at, connection_id)
    after = batch.range_after
    for skipped in sorted(batch.skipped_ids):
        if after < skipped - 1:
            spans.append((after, skipped - 1, current))
        after = skipped
    if after < batch.range_through:
        spans.append((after, batch.range_through, current))
    if not spans:
        return
    # Sweep the endpoints, choosing the newest active observation. Persist
    # disjoint spans so repeated full/incremental scans do not grow history
    # by one row per batch forever.
    keys = sorted({key for _, _, key in spans}, key=_order)
    ranks = {key: rank for rank, key in enumerate(keys)}
    starts: dict[int, list[tuple[int, int]]] = {}
    bounds: set[int] = set()
    for start, end, key in spans:
        starts.setdefault(start, []).append((-ranks[key], end))
        bounds.update((start, end))
    ordered = sorted(bounds)
    active: list[tuple[int, int]] = []
    merged: list[tuple[int, int, SpanKey]] = []
    for start, end in zip(ordered, ordered[1:]):
        for span in starts.get(start, ()):
            heappush(active, span)
        while active and active[0][1] <= start:
            heappop(active)
        if not active:
            continue
        key = keys[-active[0][0]]
        if merged and merged[-1][1:] == (start, key):
            merged[-1] = (merged[-1][0], end, key)
        else:
            merged.append((start, end, key))
    stored.delete()
    PromotionImportObservation.objects.bulk_create(
        [
            PromotionImportObservation(
                connection_id=source,
                organization_id=org_id,
                source=ReceiptSource.CONTACT_LOG,
                after=start,
                through=end,
                observed_at=observed,
            )
            for start, end, (observed, source) in merged
        ]
    )
