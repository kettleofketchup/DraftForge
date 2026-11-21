from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.db.models import QuerySet

from app.models import CustomUser, Organization
from events.models import Event, EventSignup
from org.feature_keys import FeatureKey
from org.models import OrgUser
from org.standing.base import TrackBase
from org.standing.cache import StandingCache
from org.standing.periods import Period
from org.standing.types import (
    CloseSource,
    HasUserId,
    HookName,
    Leaderboard,
    LeaderboardRow,
    Metric,
    OutputKeys,
    TrackAccess,
    TrackOutput,
    ViewerRoles,
)

FAKE_POINTS = Metric(
    key="points", label="Points", format="int", periodic=True, default=True
)

_COUNTED_HOOKS: tuple[HookName, ...] = (
    "on_event_closed",
    "on_event_reopened",
    "on_event_deleted",
    "on_event_changed",
    "on_signup_withdrawn",
    "merge_members",
    "on_user_deleted",
)


def atomic_baseline() -> int:
    return len(transaction.get_connection().atomic_blocks)


@dataclass(frozen=True, slots=True)
class FakeCall:
    hook: str
    kwargs: dict[str, Any]
    atomic_depth: int


class FakeTrack(TrackBase):
    label = "Fake"
    metrics = (FAKE_POINTS,)

    def __init__(
        self, key: str = "fake", *, feature: FeatureKey = FeatureKey.PROMOTION
    ) -> None:
        self.key = key  # type: ignore[misc]
        self.feature = feature  # type: ignore[misc]
        declared = OutputKeys(orglog=(f"{key}_count",), log=(f"{key}_ran",))
        self.output_keys = {  # type: ignore[misc]
            **{hook: declared for hook in _COUNTED_HOOKS},
            "repoint_user": OutputKeys(orglog=(f"{key}_repointed",)),
        }
        self.calls: list[FakeCall] = []
        self.raise_on: set[str] = set()
        self.order_fn: Callable[[Sequence[Any]], list[Any]] | None = None
        self.track_access = TrackAccess(can_view_rows=True, can_view_own=True)
        self.standing_block: Callable[[OrgUser], Mapping[str, object] | None] = (
            lambda ou: {"org_user_id": ou.pk}
        )
        self.board_rows: tuple[LeaderboardRow, ...] = (
            LeaderboardRow(
                org_user_id=1,
                member={"org_user_pk": 1},
                value=5,
                sample=1,
                status="ranked",
            ),
        )

    @property
    def hooks(self) -> list[str]:
        return [c.hook for c in self.calls]

    def _record(self, hook: str, **kwargs: Any) -> TrackOutput:
        self.calls.append(FakeCall(hook, kwargs, atomic_baseline()))
        if hook in self.raise_on:
            raise RuntimeError("fake")
        if hook == "repoint_user":
            return TrackOutput(orglog={f"{self.key}_repointed": 1})
        return TrackOutput(
            orglog={f"{self.key}_count": 1}, log={f"{self.key}_ran": True}
        )

    @override
    def on_event_closed(
        self,
        event: Event,
        *,
        cancelled: bool,
        source: CloseSource,
        actor: CustomUser | None,
        now: datetime,
    ) -> TrackOutput:
        return self._record(
            "on_event_closed",
            event=event,
            state=event.state,
            cancelled=cancelled,
            source=source,
            actor=actor,
            now=now,
        )

    @override
    def on_event_reopened(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        return self._record(
            "on_event_reopened", event=event, state=event.state, actor=actor, now=now
        )

    @override
    def on_event_deleted(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        exists = Event.objects.nocache().filter(pk=event.pk).exists()
        return self._record(
            "on_event_deleted", event=event, exists=exists, actor=actor, now=now
        )

    @override
    def on_event_changed(
        self, event: Event, *, fields: frozenset[str], now: datetime
    ) -> TrackOutput:
        return self._record("on_event_changed", event=event, fields=fields, now=now)

    @override
    def on_signup_withdrawn(
        self, signup: EventSignup, *, prior_status: str, by_member: bool, now: datetime
    ) -> TrackOutput:
        return self._record(
            "on_signup_withdrawn",
            signup=signup,
            prior_status=prior_status,
            by_member=by_member,
            now=now,
        )

    @override
    def on_feature_toggled(self, org_id: int, *, enabled: bool) -> None:
        self._record("on_feature_toggled", org_id=org_id, enabled=enabled)

    @override
    def merge_members(self, drop: OrgUser, keep: OrgUser) -> TrackOutput:
        exists = OrgUser.objects.filter(pk=drop.pk).exists()
        return self._record(
            "merge_members", drop=drop.pk, keep=keep.pk, drop_exists=exists
        )

    @override
    def repoint_user(self, drop: CustomUser, keep: CustomUser) -> TrackOutput:
        return self._record("repoint_user", drop=drop.pk, keep=keep.pk)

    @override
    def on_user_deleted(
        self, user: CustomUser, *, actor: CustomUser | None
    ) -> TrackOutput:
        return self._record("on_user_deleted", user=user.pk, actor=actor)

    @override
    def deletion_blockers(self, user_pks: Collection[int]) -> list[QuerySet[Any]]:
        return []

    @override
    def promotion_order[T: HasUserId](
        self, event: Event, candidates: Sequence[T], *, cache: StandingCache
    ) -> list[T]:
        if self.order_fn is None:
            return list(candidates)
        return self.order_fn(candidates)

    @override
    def access(
        self,
        org_id: int,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
    ) -> TrackAccess:
        return self.track_access

    @override
    def member_standing(
        self,
        org_user: OrgUser,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
        now: datetime,
    ) -> Mapping[str, object] | None:
        return self.standing_block(org_user)

    @override
    def leaderboard(
        self,
        org: Organization,
        metric: Metric,
        period: Period,
        *,
        viewer: CustomUser | AnonymousUser | None,
        now: datetime,
        access: TrackAccess,
    ) -> Leaderboard:
        return Leaderboard(
            track=self.key,
            metric=metric,
            period=period.label,
            rows=self.board_rows,
            total=42,
            own_row=self.board_rows[0],
            rows_visible=True,
        )
