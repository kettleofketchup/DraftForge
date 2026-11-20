from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

TrackKey = Literal["contribution", "conduct", "leadership"]
CloseSource = Literal["admin", "auto", "cancel"]
MetricFormat = Literal["int", "percent", "score5"]
HookName = Literal[
    "on_event_closed",
    "on_event_reopened",
    "on_event_deleted",
    "on_event_changed",
    "on_signup_withdrawn",
    "merge_members",
    "repoint_user",
    "on_user_deleted",
]

LogValue = int | bool


@dataclass(frozen=True, slots=True)
class OutputKeys:
    orglog: frozenset[str] = frozenset()
    log: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class TrackOutput:
    orglog: Mapping[str, LogValue] = field(default_factory=dict)
    log: Mapping[str, LogValue] = field(default_factory=dict)


EMPTY_OUTPUT = TrackOutput()


@dataclass(frozen=True, slots=True)
class HookResult:
    by_track: Mapping[str, TrackOutput] = field(default_factory=dict)

    def orglog_details(self) -> dict[str, LogValue]:
        merged: dict[str, LogValue] = {}
        for output in self.by_track.values():
            merged.update(output.orglog)
        return merged

    def log_fields(self) -> dict[str, LogValue]:
        merged: dict[str, LogValue] = {}
        for output in self.by_track.values():
            merged.update(output.log)
        return merged


@dataclass(frozen=True, slots=True)
class Metric:
    key: str
    label: str
    format: MetricFormat
    periodic: bool
    descending: bool = True
    default: bool = False


@dataclass(frozen=True, slots=True)
class TrackInfo:
    key: TrackKey
    label: str
    metrics: tuple[Metric, ...]
    can_view_rows: bool
    can_view_own: bool
    can_manage: bool


@dataclass(frozen=True, slots=True)
class LeaderboardRow:
    org_user_id: int
    member: Mapping[str, object]
    value: float | int
    sample: int
    status: Literal["ranked", "new"]


@dataclass(frozen=True, slots=True)
class Leaderboard:
    track: TrackKey
    metric: Metric
    period: str
    rows: Sequence[LeaderboardRow]
    total: float | int | None
    own_row: LeaderboardRow | None
