from collections.abc import Callable

from org.standing.types import TrackKey


class StandingCache:
    """Opaque per-request memo passed through promotion_order."""

    __slots__ = ("_memo",)

    def __init__(self) -> None:
        self._memo: dict[tuple[str, str], object] = {}


def memo[T](
    cache: StandingCache, track: TrackKey, name: str, compute: Callable[[], T]
) -> T:
    key = (track, name)
    if key not in cache._memo:
        cache._memo[key] = compute()
    return cache._memo[key]  # type: ignore[return-value]
