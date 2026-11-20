from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, override

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet

from app.models import CustomUser, Organization
from app.permissions_org import can_view_org_members
from events.models import Event
from org.contributions.kinds import EVENT_STAFF_KINDS
from org.contributions.queries import leaderboard as contribution_leaderboard
from org.contributions.queries import org_total
from org.contributions.services import (
    delete_user_entries,
    reassign_member,
    repoint_ledger_attribution,
    should_sync_staff,
    sync_event_staff_entries,
    user_entries,
)
from org.feature_keys import FeatureKey
from org.models import OrgUser
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
        return [user_entries(user_pks)]

    @override
    def access(
        self, org_id: int, *, viewer: CustomUser | AnonymousUser | None
    ) -> TrackAccess:
        return TrackAccess(
            can_view_rows=viewer is not None and can_view_org_members(viewer, org_id),
            can_view_own=bool(viewer is not None and viewer.is_authenticated),
        )

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
                    value=row["points"],
                    sample=row["entries"],
                    status="ranked",
                )
                for row in contribution_leaderboard(org, period)
            ]
            if access.can_view_rows
            else []
        )
        return Leaderboard(
            track=self.key,
            metric=metric,
            period=period.label,
            rows=rows,
            total=total,
            own_row=None,
            rows_visible=access.can_view_rows,
        )


CONTRIBUTION = ContributionTrack()
