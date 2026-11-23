from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Literal, Protocol, runtime_checkable

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
    orglog: tuple[str, ...] = ()
    log: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrackOutput:
    orglog: Mapping[str, LogValue] = field(default_factory=dict)
    log: Mapping[str, LogValue] = field(default_factory=dict)


EMPTY_OUTPUT = TrackOutput()


@dataclass(frozen=True, slots=True)
class HookResult:
    by_track: Mapping[TrackKey, TrackOutput] = field(default_factory=dict)

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
    board_open: bool
    can_manage: bool
    can_moderate: bool


RoleCheck = Callable[[], bool]


class ViewerRoles:
    def __init__(
        self, *, is_admin: RoleCheck, is_staff: RoleCheck, can_view_members: RoleCheck
    ) -> None:
        self._is_admin = is_admin
        self._is_staff = is_staff
        self._can_view_members = can_view_members

    @classmethod
    def fixed(
        cls, is_admin: bool, is_staff: bool, can_view_members: bool
    ) -> "ViewerRoles":
        return cls(
            is_admin=lambda: is_admin,
            is_staff=lambda: is_staff,
            can_view_members=lambda: can_view_members,
        )

    @cached_property
    def is_admin(self) -> bool:
        return self._is_admin()

    @cached_property
    def is_staff(self) -> bool:
        return self._is_staff()

    @cached_property
    def can_view_members(self) -> bool:
        return self._can_view_members()


@dataclass(frozen=True, slots=True)
class TrackAccess:
    can_view_rows: bool
    can_view_own: bool
    allowed: bool = True
    board_open: bool = True


@dataclass(frozen=True, slots=True)
class LeaderboardRow:
    org_user_id: int
    member: Mapping[str, object]
    value: float | int | None
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
    rows_visible: bool


@runtime_checkable
class HasUserId(Protocol):
    user_id: int
