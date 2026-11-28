"""Range-aware scan ordering, including source IDs never stored as receipts.

All reads/writes run under the importing organization's transaction lock.
Only successfully committed coverage is retained; skipped IDs stay holes.
"""

from __future__ import annotations

from heapq import heappop, heappush
from typing import TYPE_CHECKING

from org.models_promotion_sync import PromotionImportObservation, ReceiptSource

if TYPE_CHECKING:
    from org.integration.contacts import ImportBatch


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


def record_ranges(
    org_id: int, batch: ImportBatch, *, connection_id: int | None = None
) -> None:
    if batch.range_through is None:
        return
    stored = PromotionImportObservation.objects.filter(
        organization_id=org_id, source=ReceiptSource.CONTACT_LOG
    )
    rows = list(stored.values_list("after", "through", "observed_at", "connection_id"))
    spans = [(after, through, observed) for after, through, observed, _ in rows]
    sources = {observed: source for _, _, observed, source in rows}
    sources[batch.scan_started_at] = connection_id
    after = batch.range_after
    for skipped in sorted(batch.skipped_ids):
        if after < skipped - 1:
            spans.append((after, skipped - 1, batch.scan_started_at))
        after = skipped
    if after < batch.range_through:
        spans.append((after, batch.range_through, batch.scan_started_at))
    if not spans:
        return
    # Sweep the endpoints, choosing the newest active observation. Persist
    # disjoint spans so repeated full/incremental scans do not grow history
    # by one row per batch forever.
    times = sorted({observed for _, _, observed in spans})
    ranks = {observed: rank for rank, observed in enumerate(times)}
    starts = {}
    bounds = set()
    for start, end, observed in spans:
        starts.setdefault(start, []).append((-ranks[observed], end))
        bounds.update((start, end))
    bounds = sorted(bounds)
    active = []
    merged = []
    for start, end in zip(bounds, bounds[1:]):
        for span in starts.get(start, ()):
            heappush(active, span)
        while active and active[0][1] <= start:
            heappop(active)
        if not active:
            continue
        observed = times[-active[0][0]]
        if merged and merged[-1][1:] == (start, observed):
            merged[-1] = (merged[-1][0], end, observed)
        else:
            merged.append((start, end, observed))
    stored.delete()
    PromotionImportObservation.objects.bulk_create(
        [
            PromotionImportObservation(
                connection_id=sources.get(observed),
                organization_id=org_id,
                source=ReceiptSource.CONTACT_LOG,
                after=start,
                through=end,
                observed_at=observed,
            )
            for start, end, observed in merged
        ]
    )
