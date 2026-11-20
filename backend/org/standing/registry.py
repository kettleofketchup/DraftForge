from collections.abc import Iterator
from contextlib import contextmanager

from org.contributions.adapter import CONTRIBUTION
from org.standing.base import TrackBase
from org.standing.errors import UnknownTrack


def validate(tracks: tuple[TrackBase, ...]) -> None:
    keys = [t.key for t in tracks]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate track key in {keys}")
    for t in tracks:
        defaults = [m for m in t.metrics if m.default]
        if len(defaults) != 1:
            raise ValueError(f"track {t.key!r} needs exactly one default metric")
    seen: dict[tuple[str, str, str], str] = {}
    for t in tracks:
        for hook, declared in t.output_keys.items():
            for channel, names in (("orglog", declared.orglog), ("log", declared.log)):
                for name in names:
                    slot = (hook, channel, name)
                    if slot in seen:
                        raise ValueError(
                            f"tracks {seen[slot]!r} and {t.key!r} both declare "
                            f"{channel} key {name!r} for {hook}"
                        )
                    seen[slot] = t.key


TRACKS: tuple[TrackBase, ...] = (CONTRIBUTION,)
validate(TRACKS)

_active: tuple[TrackBase, ...] = TRACKS


def tracks() -> tuple[TrackBase, ...]:
    return _active


def track(key: str) -> TrackBase:
    for t in _active:
        if t.key == key:
            return t
    raise UnknownTrack(key)


@contextmanager
def override_tracks(*replacement: TrackBase) -> Iterator[None]:
    global _active
    validate(replacement)
    previous = _active
    _active = replacement
    try:
        yield
    finally:
        _active = previous
