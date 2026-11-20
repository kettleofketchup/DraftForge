from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, override

from django.db.models import QuerySet

from app.models import CustomUser, Organization
from app.permissions_org import can_view_org_members, has_org_admin_access
from events.models import Event
from org.contributions.queries import (
    leaderboard as contribution_leaderboard,
)
from org.contributions.queries import (
    member_monthly,
    member_totals,
    org_total,
)
from org.contributions.services import (
    delete_user_entries,
    reassign_member,
    repoint_ledger_attribution,
    revoke_event_staff_entries,
    should_sync_staff,
    sync_event_staff_entries,
    user_entries,
)
from org.feature_keys import FeatureKey
from org.models import OrgUser
from org.standing.base import TrackBase
from org.standing.periods import Period
from org.standing.types import (
    CloseSource,
    HookName,
    Leaderboard,
    LeaderboardRow,
    Metric,
    OutputKeys,
    TrackInfo,
    TrackOutput,
)

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
        "on_event_reopened": OutputKeys(orglog=("revoked",)),
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
        return TrackOutput(orglog={"revoked": revoke_event_staff_entries(event)})

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
        return [user_entries(user_pks)]

    @override
    def track_info(self, org: Organization, *, viewer: CustomUser | None) -> TrackInfo:
        is_member = viewer is not None and viewer.is_authenticated
        return TrackInfo(
            key=self.key,
            label=self.label,
            metrics=self.metrics,
            can_view_rows=viewer is not None and can_view_org_members(viewer, org),
            can_view_own=is_member,
            can_manage=viewer is not None and has_org_admin_access(viewer, org),
        )

    @override
    def leaderboard(
        self,
        org: Organization,
        metric: Metric,
        period: Period,
        *,
        viewer: CustomUser | None,
        now: datetime,
    ) -> Leaderboard:
        rows = [
            LeaderboardRow(
                org_user_id=row["org_user_pk"],
                member={k: v for k, v in row.items() if k not in ("points", "entries")},
                value=row[metric.key],  # type: ignore[literal-required]
                sample=row["entries"],
                status="ranked",
            )
            for row in contribution_leaderboard(org, period)
        ]
        if metric.key == "entries":
            rows.sort(key=lambda r: -r.value)
        return Leaderboard(
            track=self.key,
            metric=metric,
            period=period.label,
            rows=rows,
            total=org_total(org, period),
            own_row=None,
            rows_visible=True,
        )

    @override
    def member_standing(
        self, org_user: OrgUser, *, viewer: CustomUser | None, now: datetime
    ) -> Mapping[str, object]:
        return {
            "totals": member_totals(org_user, now=now),
            "monthly": member_monthly(org_user, now=now),
        }


CONTRIBUTION = ContributionTrack()
