from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, override

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet

from app.models import CustomUser
from events.models import Event
from org.contributions.kinds import EVENT_STAFF_KINDS
from org.contributions.queries import leaderboard as contribution_leaderboard
from org.contributions.queries import (
    member_overview,
    org_total,
    own_org_user,
    own_totals,
)
from org.contributions.serializers import member_summary
from org.contributions.services import (
    delete_user_entries,
    reassign_member,
    repoint_ledger_attribution,
    should_sync_staff,
    sync_event_staff_entries,
)
from org.feature_keys import FeatureKey
from org.models import Organization, OrgUser
from org.standing import ledger
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

_SORT_FIELDS: Mapping[str, ledger.SortField] = {
    "points": "total",
    "entries": "entries",
}

STAFF_FIELDS: frozenset[str] = frozenset(
    {"scheduled_at", "ends_at", "name", "host", "helpers"}
)


def _should_award(event: Event, *, cancelled: bool, source: CloseSource) -> bool:
    if not cancelled:
        return True
    if source != "auto":
        return False
    return event.host_id is not None or event.helpers.nocache().exists()


class ContributionTrack(TrackBase):
    key = "contribution"
    label = "Contributions"
    feature = FeatureKey.CONTRIBUTIONS
    metrics = (
        Metric(key="points", label="Points", format="int", periodic=True, default=True),
        Metric(key="entries", label="Entries", format="int", periodic=True),
    )
    reopen_reset_fields = ("contributions_awarded_at",)
    output_keys: Mapping[HookName, OutputKeys] = {
        "on_event_closed": OutputKeys(orglog=("awarded",), log=("awarded", "created")),
        "on_event_reopened": OutputKeys(orglog=("revoked",), log=("revoked",)),
        "on_event_changed": OutputKeys(log=("synced",)),
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
        if not _should_award(event, cancelled=cancelled, source=source):
            return TrackOutput(
                orglog={"awarded": 0}, log={"awarded": False, "created": 0}
            )
        sync = sync_event_staff_entries(event)
        Event.objects.nocache().filter(pk=event.pk).update(contributions_awarded_at=now)
        event.contributions_awarded_at = now
        return TrackOutput(
            orglog={"awarded": sync.created},
            log={"awarded": True, "created": sync.created},
        )

    @override
    def on_event_reopened(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        revoked = ledger.revoke_event_kinds(event, kinds=EVENT_STAFF_KINDS)
        return TrackOutput(orglog={"revoked": revoked}, log={"revoked": revoked})

    @override
    def on_event_changed(
        self, event: Event, *, fields: frozenset[str], now: datetime
    ) -> TrackOutput:
        synced = should_sync_staff(event)
        if synced and fields & STAFF_FIELDS:
            sync_event_staff_entries(event)
        return TrackOutput(log={"synced": synced})

    @override
    def merge_members(self, drop: OrgUser, keep: OrgUser) -> TrackOutput:
        reassign_member(drop, keep)
        return TrackOutput()

    @override
    def repoint_user(self, drop: CustomUser, keep: CustomUser) -> TrackOutput:
        repoint_ledger_attribution(drop, keep)
        return TrackOutput()

    @override
    def on_user_deleted(
        self, user: CustomUser, *, actor: CustomUser | None
    ) -> TrackOutput:
        delete_user_entries(user, actor=actor)
        return TrackOutput()

    @override
    def deletion_blockers(self, user_pks: Collection[int]) -> list[QuerySet[Any]]:
        return [ledger.user_rows(user_pks)]

    @override
    def access(
        self,
        org_id: int,
        *,
        viewer: CustomUser | AnonymousUser | None,
        roles: ViewerRoles,
    ) -> TrackAccess:
        return TrackAccess(
            can_view_rows=roles.can_view_members,
            can_view_own=bool(viewer is not None and viewer.is_authenticated),
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
        if org_user.user_id != viewer.pk and not roles.can_view_members:
            return None
        return member_overview(org_user, now=now)

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
        total = org_total(org, period)
        rows = (
            [
                LeaderboardRow(
                    org_user_id=row["org_user_pk"],
                    member={
                        k: v for k, v in row.items() if k not in ("points", "entries")
                    },
                    value=row["entries"] if metric.key == "entries" else row["points"],
                    sample=row["entries"],
                    status="ranked",
                )
                for row in contribution_leaderboard(
                    org, period, sort=_SORT_FIELDS[metric.key]
                )
            ]
            if access.can_view_rows
            else []
        )
        own = own_org_user(viewer, org)
        totals = own_totals(own, period) if own is not None else None
        own_row = None
        if own is not None and totals is not None:
            points, entries = totals
            own_row = LeaderboardRow(
                org_user_id=own.pk,
                member=member_summary(own),
                value=entries if metric.key == "entries" else points,
                sample=entries,
                status="ranked",
            )
        return Leaderboard(
            track=self.key,
            metric=metric,
            period=period.label,
            rows=rows,
            total=total,
            own_row=own_row,
            rows_visible=access.can_view_rows,
        )


CONTRIBUTION = ContributionTrack()
