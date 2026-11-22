from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from org.conduct.adapter import CONDUCT
from org.contributions.adapter import CONTRIBUTION
from org.leadership.adapter import LEADERSHIP
from org.standing.base import TrackBase
from org.standing.errors import UnknownTrack

_MERGE_HOOKS: frozenset[str] = frozenset({"merge_members", "repoint_user"})


def _namespace(hook: str) -> str:
    return "merge" if hook in _MERGE_HOOKS else hook


def validate_tracks(tracks: Sequence[TrackBase]) -> None:
    keys = [t.key for t in tracks]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate track key in {keys}")
    seen: dict[tuple[str, str, str], tuple[str, str]] = {}
    for t in tracks:
        if len([m for m in t.metrics if m.default]) != 1:
            raise ValueError(f"track {t.key!r} needs exactly one default metric")
        for hook, declared in t.output_keys.items():
            for channel, names in (("orglog", declared.orglog), ("log", declared.log)):
                for name in names:
                    slot = (_namespace(hook), channel, name)
                    if slot in seen:
                        owner, owner_hook = seen[slot]
                        raise ValueError(
                            f"{channel} key {name!r} declared by {owner!r} on "
                            f"{owner_hook} and by {t.key!r} on {hook}"
                        )
                    seen[slot] = (t.key, hook)


TRACKS: tuple[TrackBase, ...] = (CONTRIBUTION, CONDUCT, LEADERSHIP)
validate_tracks(TRACKS)

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
    validate_tracks(replacement)
    previous = _active
    _active = replacement
    try:
        yield
    finally:
        _active = previous
