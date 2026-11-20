from collections.abc import Callable


class StandingCache:
    """Per-request memo shared by promotion_order and the eligibility check."""

    __slots__ = ("_values",)

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], object] = {}


def get_or_compute[V](
    cache: StandingCache, track: str, name: str, compute: Callable[[], V]
) -> V:
    key = (track, name)
    if key not in cache._values:
        cache._values[key] = compute()
    return cache._values[key]  # type: ignore[return-value]
