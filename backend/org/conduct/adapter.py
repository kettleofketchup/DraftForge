from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import override

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from app.models import CustomUser, Organization
from app.permissions_org import can_view_org_members, has_org_staff_access
from events.models import Event, EventSignup
from org.conduct.capture import capture_late_cancel
from org.conduct.eligibility import gate_for, standings
from org.conduct.enforcement import defer_back_of_line
from org.conduct.finalize import finalize_event_outcomes
from org.conduct.gate import get_conduct_settings
from org.conduct.leaderboard import conduct_board
from org.conduct.lifecycle import (
    reopen_event_outcomes,
    teardown_event_outcomes,
    void_event_outcomes,
)
from org.conduct.queries import member_scores
from org.conduct.scoring import MemberScore
from org.conduct.serializers import rate
from org.conduct.services import reassign_member, refresh_org_unmet_on_commit
from org.contributions.serializers import member_summary
from org.feature_keys import FeatureKey
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings
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
    TrackInfo,
    TrackOutput,
    ViewerRoles,
)


def _is_member(viewer: CustomUser | AnonymousUser | None, org_id: int) -> bool:
    if viewer is None or not viewer.is_authenticated:
        return False
    return OrgUser.objects.filter(organization_id=org_id, user_id=viewer.pk).exists()


def _row(org_user: OrgUser, score: MemberScore) -> LeaderboardRow:
    return LeaderboardRow(
        org_user_id=org_user.pk,
        member=member_summary(org_user),
        value=rate(score.show_rate),
        sample=score.counted_events,
        status="new" if score.status == "new" else "ranked",
    )


class ConductTrack(TrackBase):
    key = "conduct"
    label = "Conduct"
    feature = FeatureKey.CONDUCT
    metrics = (
        Metric(
            key="show_rate",
            label="Show rate",
            format="percent",
            periodic=False,
            default=True,
        ),
    )
    reopen_reset_fields = ("conduct_finalized_at",)
    output_keys: Mapping[HookName, OutputKeys] = {
        "on_event_reopened": OutputKeys(orglog=("attendance_reopened",)),
    }

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
        logged_actor = None if source == "auto" else actor
        if cancelled:
            void_event_outcomes(event, now=now, actor=logged_actor)
        else:
            finalize_event_outcomes(event, now=now, actor=logged_actor)
        event.conduct_finalized_at = (
            Event.objects.nocache()
            .filter(pk=event.pk)
            .values_list("conduct_finalized_at", flat=True)
            .first()
        )
        return TrackOutput()

    @override
    def on_event_reopened(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        deleted, kept = reopen_event_outcomes(event)
        return TrackOutput(orglog={"attendance_reopened": deleted + kept})

    @override
    def on_event_deleted(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        teardown_event_outcomes(event, actor=actor, now=now)
        return TrackOutput()

    @override
    def on_signup_withdrawn(
        self, signup: EventSignup, *, prior_status: str, by_member: bool, now: datetime
    ) -> TrackOutput:
        if by_member:
            capture_late_cancel(signup, prior_status=prior_status, now=now)
        return TrackOutput()

    @override
    def on_feature_toggled(self, org_id: int, *, enabled: bool) -> None:
        refresh_org_unmet_on_commit(org_id)

    @override
    def merge_members(self, drop: OrgUser, keep: OrgUser) -> TrackOutput:
        reassign_member(drop, keep)
        return TrackOutput()

    @override
    def repoint_user(self, drop: CustomUser, keep: CustomUser) -> TrackOutput:
        AttendanceOutcome.objects.nocache().filter(set_by=drop).update(set_by=keep)
        OrgConductSettings.objects.nocache().filter(updated_by=drop).update(
            updated_by=keep
        )
        return TrackOutput()

    @override
    def promotion_order[T: HasUserId](
        self, event: Event, candidates: Sequence[T], *, cache: StandingCache
    ) -> list[T]:
        org_id = event.organization_id
        if org_id is None or not candidates:
            return list(candidates)
        if not gate_for(org_id, cache).back_of_line:
            return list(candidates)
        found = standings(
            org_id,
            [c.user_id for c in candidates],
            now=timezone.now(),
            cache=cache,
        )
        deferred = {user_id for user_id, s in found.items() if s.deferred}
        return defer_back_of_line(candidates, deferred)

    @override
    def access(
        self, org_id: int, *, viewer: CustomUser | AnonymousUser | None
    ) -> TrackAccess:
        settings = get_conduct_settings(org_id)
        board = viewer is not None and (
            settings.leaderboard_public
            or has_org_staff_access(viewer, Organization.objects.get(pk=org_id))
        )
        return TrackAccess(
            can_view_rows=bool(board and can_view_org_members(viewer, org_id)),
            can_view_own=_is_member(viewer, org_id),
        )

    @override
    def track_info(
        self,
        org_id: int,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
    ) -> TrackInfo:
        public = get_conduct_settings(org_id).leaderboard_public
        return TrackInfo(
            key=self.key,
            label=self.label,
            metrics=self.metrics,
            can_view_rows=public or roles.is_staff,
            can_view_own=_is_member(viewer, org_id),
            can_manage=roles.is_admin,
        )

    @override
    def member_standing(
        self,
        org_user: OrgUser,
        *,
        viewer: CustomUser | AnonymousUser | None,
        now: datetime,
    ) -> Mapping[str, object] | None:
        if viewer is None or not viewer.is_authenticated:
            return None
        org_id = org_user.organization_id
        if org_user.user_id != viewer.pk and not has_org_staff_access(
            viewer, org_user.organization
        ):
            return None
        settings = get_conduct_settings(org_id)
        score = member_scores(org_id, [org_user.pk], now=now, settings=settings)[
            org_user.pk
        ]
        return {
            "show_rate": rate(score.show_rate),
            "status": score.status,
            "counted_events": score.counted_events,
        }

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
        settings = get_conduct_settings(org)
        board = conduct_board(org, settings=settings, now=now)
        rows = [_row(m, s) for m, s, _ in board.ranked] + [
            _row(m, s) for m, s in board.new
        ]
        own_row = None
        if viewer is not None and viewer.is_authenticated:
            own_row = next(
                (row for row in rows if row.member.get("user_pk") == viewer.pk), None
            )
        return Leaderboard(
            track=self.key,
            metric=metric,
            period="current",
            rows=rows if access.can_view_rows else [],
            total=None,
            own_row=own_row,
            rows_visible=access.can_view_rows,
        )


CONDUCT = ConductTrack()
