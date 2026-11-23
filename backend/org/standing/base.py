import abc
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, ClassVar

from django.contrib.auth.models import AnonymousUser
from django.db.models import Expression, QuerySet

from app.models import CustomUser
from events.models import Event, EventSignup
from org.feature_keys import FeatureKey
from org.models import Organization, OrgUser
from org.standing.cache import StandingCache
from org.standing.periods import Period
from org.standing.types import (
    EMPTY_OUTPUT,
    CloseSource,
    HasUserId,
    HookName,
    Leaderboard,
    Metric,
    OutputKeys,
    TrackAccess,
    TrackInfo,
    TrackKey,
    TrackOutput,
    ViewerRoles,
)


class TrackBase(abc.ABC):
    key: ClassVar[TrackKey]
    label: ClassVar[str]
    feature: ClassVar[FeatureKey]
    metrics: ClassVar[tuple[Metric, ...]]
    reopen_reset_fields: ClassVar[tuple[str, ...]] = ()
    output_keys: ClassVar[Mapping[HookName, OutputKeys]] = {}
    moderated: ClassVar[bool] = False

    def on_event_closed(
        self,
        event: Event,
        *,
        cancelled: bool,
        source: CloseSource,
        actor: CustomUser | None,
        now: datetime,
    ) -> TrackOutput:
        return EMPTY_OUTPUT

    def on_event_reopened(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        return EMPTY_OUTPUT

    def on_event_deleted(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        return EMPTY_OUTPUT

    def on_event_changed(
        self, event: Event, *, fields: frozenset[str], now: datetime
    ) -> TrackOutput:
        return EMPTY_OUTPUT

    def on_signup_withdrawn(
        self, signup: EventSignup, *, prior_status: str, by_member: bool, now: datetime
    ) -> TrackOutput:
        return EMPTY_OUTPUT

    def on_feature_toggled(self, org_id: int, *, enabled: bool) -> None:
        return None

    def merge_members(self, drop: OrgUser, keep: OrgUser) -> TrackOutput:
        return EMPTY_OUTPUT

    def repoint_user(self, drop: CustomUser, keep: CustomUser) -> TrackOutput:
        return EMPTY_OUTPUT

    def on_user_deleted(
        self, user: CustomUser, *, actor: CustomUser | None
    ) -> TrackOutput:
        return EMPTY_OUTPUT

    def deletion_blockers(self, user_pks: Collection[int]) -> list[QuerySet[Any]]:
        return []

    def promotion_order[T: HasUserId](
        self, event: Event, candidates: Sequence[T], *, cache: StandingCache
    ) -> list[T]:
        return list(candidates)

    def metrics_for(self, org_id: int) -> tuple[Metric, ...]:
        return self.metrics

    def event_viewer_flags(
        self, event_id: int, *, now: datetime
    ) -> Mapping[str, Expression]:
        """Flag expressions annotated on the viewer's OrgUser row (OuterRef("pk"))."""
        return {}

    @abc.abstractmethod
    def access(
        self,
        org_id: int,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
    ) -> TrackAccess: ...

    @abc.abstractmethod
    def leaderboard(
        self,
        org: Organization,
        metric: Metric,
        period: Period,
        *,
        viewer: CustomUser | AnonymousUser | None,
        now: datetime,
        access: TrackAccess,
    ) -> Leaderboard: ...

    @abc.abstractmethod
    def member_standing(
        self,
        org_user: OrgUser,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
        now: datetime,
    ) -> Mapping[str, object] | None: ...

    def track_info(
        self,
        org_id: int,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
    ) -> TrackInfo:
        access = self.access(org_id, viewer=viewer, roles=roles)
        return TrackInfo(
            key=self.key,
            label=self.label,
            metrics=self.metrics_for(org_id),
            can_view_rows=access.can_view_rows,
            can_view_own=access.can_view_own,
            board_open=access.board_open,
            can_manage=roles.is_admin,
            can_moderate=self.moderated and roles.is_staff,
        )
