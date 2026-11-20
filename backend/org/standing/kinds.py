from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from org.contributions.kinds import DEFAULT_POINTS, EVENT_STAFF_KINDS, ContributionKind
from org.standing.types import TrackKey


@dataclass(frozen=True, slots=True)
class LedgerKind:
    track: TrackKey
    default_points: int | None
    once_per_event: bool
    formula: bool = False


CONTRIBUTION_KINDS: tuple[tuple[str, LedgerKind], ...] = tuple(
    (
        kind.value,
        LedgerKind(
            track="contribution",
            default_points=DEFAULT_POINTS.get(kind.value),
            once_per_event=kind in EVENT_STAFF_KINDS,
        ),
    )
    for kind in ContributionKind
)


def build_kinds(*groups: Iterable[tuple[str, LedgerKind]]) -> dict[str, LedgerKind]:
    table: dict[str, LedgerKind] = {}
    for group in groups:
        for name, kind in group:
            if name in table:
                raise ValueError(f"duplicate ledger kind {name!r}")
            table[name] = kind
    return table


KINDS: Mapping[str, LedgerKind] = build_kinds(CONTRIBUTION_KINDS)


def kinds_for(track: TrackKey) -> frozenset[str]:
    return frozenset(name for name, kind in KINDS.items() if kind.track == track)


ONCE_PER_EVENT_KINDS: frozenset[str] = frozenset(
    name for name, kind in KINDS.items() if kind.once_per_event
)
