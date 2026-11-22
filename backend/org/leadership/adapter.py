from collections.abc import Mapping
from datetime import datetime
from typing import override

from django.contrib.auth.models import AnonymousUser
from django.db.models import Exists, OuterRef
from django.utils import timezone

from app.models import CustomUser
from events.models import Event
from org.contributions.serializers import member_summary
from org.feature_keys import FeatureKey
from org.leadership import lifecycle, maintenance
from org.leadership.queries import CaptainRating, points_board, rating_board
from org.leadership.rating import display
from org.leadership.settings import get_leadership_settings
from org.leadership.summary import member_payload
from org.leadership.traits import effective_traits
from org.models import Organization, OrgUser
from org.models_leadership import CaptainReview, EventCaptain
from org.standing.base import TrackBase
from org.standing.periods import Period
from org.standing.types import (
    CloseSource,
    HookName,
    Leaderboard,
    LeaderboardRow,
    Metric,
    OutputKeys,
    TrackAccess,
    TrackOutput,
    ViewerRoles,
)
from user.querysets import with_user_profiles

LEADERBOARD_LIMIT = 100
TRAIT_METRIC_PREFIX = "rating."


def _is_member(viewer: CustomUser | AnonymousUser | None, org_id: int) -> bool:
    if viewer is None or not viewer.is_authenticated:
        return False
    return OrgUser.objects.filter(organization_id=org_id, user_id=viewer.pk).exists()


def _close_output(
    *, snapshotted: int, awarded: int, voided: int, revoked: int
) -> TrackOutput:
    return TrackOutput(
        orglog={"captains_snapshotted": snapshotted, "leadership_awarded": awarded},
        log={"captain_reviews_voided": voided, "leadership_revoked": revoked},
    )


class LeadershipTrack(TrackBase):
    key = "leadership"
    label = "Leadership"
    feature = FeatureKey.LEADERSHIP
    metrics = (
        Metric(
            key="rating", label="Rating", format="score5", periodic=False, default=True
        ),
        Metric(key="points", label="Points", format="int", periodic=True),
    )
    output_keys: Mapping[HookName, OutputKeys] = {
        "on_event_closed": OutputKeys(
            orglog=("captains_snapshotted", "leadership_awarded"),
            log=("captain_reviews_voided", "leadership_revoked"),
        ),
        "on_event_reopened": OutputKeys(
            orglog=("captain_reviews_voided", "leadership_revoked")
        ),
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
        if cancelled:
            voided = lifecycle.void_event(event, now=now)
            return _close_output(
                snapshotted=0,
                awarded=0,
                voided=voided.reviews_voided,
                revoked=voided.revoked,
            )
        result = lifecycle.snapshot_event(event, now=now)
        return _close_output(
            snapshotted=result.captains, awarded=result.awarded, voided=0, revoked=0
        )

    @override
    def on_event_reopened(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        result = lifecycle.void_event(event, now=now)
        return TrackOutput(
            orglog={
                "captain_reviews_voided": result.reviews_voided,
                "leadership_revoked": result.revoked,
            }
        )

    @override
    def on_event_deleted(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        lifecycle.delete_event_rows(event)
        return TrackOutput()

    @override
    def merge_members(self, drop: OrgUser, keep: OrgUser) -> TrackOutput:
        maintenance.reassign_member(drop, keep, now=timezone.now())
        return TrackOutput()

    @override
    def repoint_user(self, drop: CustomUser, keep: CustomUser) -> TrackOutput:
        maintenance.repoint_attribution(drop, keep)
        return TrackOutput()

    @override
    def on_user_deleted(
        self, user: CustomUser, *, actor: CustomUser | None
    ) -> TrackOutput:
        maintenance.delete_user_rows(user, actor=actor, now=timezone.now())
        return TrackOutput()

    @override
    def event_viewer_flags(
        self, event_id: int, viewer: OrgUser, *, now: datetime
    ) -> Mapping[str, object]:
        pending = (
            EventCaptain.objects.nocache()
            .filter(
                event_id=event_id,
                voided_at__isnull=True,
                window_closes_at__gt=now,
                teammates=viewer,
            )
            .exclude(captain=viewer)
            .exclude(
                Exists(
                    CaptainReview.objects.filter(
                        event_captain=OuterRef("pk"),
                        rater=viewer,
                        voided_at__isnull=True,
                    )
                )
            )
            .count()
        )
        return {"can_review_captains": pending > 0, "pending_captain_reviews": pending}

    @override
    def metrics_for(self, org_id: int) -> tuple[Metric, ...]:
        return self.metrics + tuple(
            Metric(
                key=f"{TRAIT_METRIC_PREFIX}{t.key}",
                label=t.label,
                format="score5",
                periodic=False,
            )
            for t in effective_traits(org_id)
            if t.active
        )

    @override
    def access(
        self,
        org_id: int,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
    ) -> TrackAccess:
        member = _is_member(viewer, org_id)
        public = get_leadership_settings(org_id).leaderboard_public
        board_open = public or roles.is_staff
        return TrackAccess(
            can_view_rows=roles.is_staff or (public and roles.can_view_members),
            can_view_own=member,
            allowed=board_open or member,
            board_open=board_open,
        )

    @override
    def member_standing(
        self,
        org_user: OrgUser,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
        now: datetime,
    ) -> Mapping[str, object] | None:
        if viewer is None or not viewer.is_authenticated:
            return None
        own = org_user.user_id == viewer.pk
        public = get_leadership_settings(org_user.organization_id).leaderboard_public
        if not (own or roles.is_staff or (public and roles.can_view_members)):
            return None
        payload = member_payload(org_user, now=now, detail=False, staff=False)
        payload.pop("member", None)
        return payload

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
        own_user_id = (
            viewer.pk if viewer is not None and viewer.is_authenticated else None
        )
        total: int | None = None
        if metric.key == "points":
            rows, own_row = self._points_rows(org, period, own_user_id, now=now)
            total = sum(int(r.value or 0) for r in rows)
            label = period.label
        else:
            rows, own_row = self._rating_rows(org, metric, own_user_id, now=now)
            label = "current"
        if own_row is None and access.can_view_own and own_user_id is not None:
            own_row = self._unrated_row(org, own_user_id)
        return Leaderboard(
            track=self.key,
            metric=metric,
            period=label,
            rows=rows[:LEADERBOARD_LIMIT] if access.can_view_rows else [],
            total=total,
            own_row=own_row if access.can_view_own else None,
            rows_visible=access.can_view_rows,
        )

    @staticmethod
    def _unrated_row(org: Organization, user_id: int) -> LeaderboardRow | None:
        member = with_user_profiles(
            OrgUser.objects.filter(organization=org, user_id=user_id), "user"
        ).first()
        if member is None:
            return None
        return LeaderboardRow(
            org_user_id=member.pk,
            member=member_summary(member),
            value=None,
            sample=0,
            status="new",
        )

    @staticmethod
    def _members(org: Organization, pks: list[int]) -> dict[int, OrgUser]:
        return with_user_profiles(
            OrgUser.objects.filter(organization=org, pk__in=pks), "user"
        ).in_bulk()

    def _points_rows(
        self,
        org: Organization,
        period: Period,
        own_user_id: int | None,
        *,
        now: datetime,
    ) -> tuple[list[LeaderboardRow], LeaderboardRow | None]:
        sums = list(points_board(org.pk, period, now=now))
        members = self._members(org, [s["org_user"] for s in sums])
        rows = [
            LeaderboardRow(
                org_user_id=s["org_user"],
                member=member_summary(members[s["org_user"]]),
                value=s["total"],
                sample=s["entries"],
                status="ranked",
            )
            for s in sums
            if s["org_user"] in members
        ]
        own = next(
            (r for r in rows if members[r.org_user_id].user_id == own_user_id), None
        )
        return rows, own

    def _rating_rows(
        self,
        org: Organization,
        metric: Metric,
        own_user_id: int | None,
        *,
        now: datetime,
    ) -> tuple[list[LeaderboardRow], LeaderboardRow | None]:
        settings = get_leadership_settings(org)
        traits = effective_traits(org)
        ratings = rating_board(org.pk, now=now, settings=settings, traits=traits)
        trait_pk = None
        if metric.key.startswith(TRAIT_METRIC_PREFIX):
            wanted = metric.key.removeprefix(TRAIT_METRIC_PREFIX)
            trait_pk = next((t.pk for t in traits if t.key == wanted), None)

        def value(rating: CaptainRating) -> float | None:
            raw = rating.overall if trait_pk is None else rating.traits.get(trait_pk)
            return display(raw)

        members = self._members(org, list(ratings))
        scored = [
            (pk, r, value(r))
            for pk, r in ratings.items()
            if pk in members and value(r) is not None
        ]
        scored.sort(key=lambda item: (-(item[2] or 0), members[item[0]].user.username))
        rows = [
            LeaderboardRow(
                org_user_id=pk,
                member=member_summary(members[pk]),
                value=v,
                sample=r.reviews,
                status=r.status,
            )
            for pk, r, v in scored
        ]
        own = next(
            (r for r in rows if members[r.org_user_id].user_id == own_user_id), None
        )
        ranked = [r for r in rows if r.status == "ranked"]
        return ranked, own


LEADERSHIP = LeadershipTrack()
