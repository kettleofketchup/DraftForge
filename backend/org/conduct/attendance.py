from datetime import datetime
from typing import Literal, TypedDict

from rest_framework import serializers

from app.models import CustomUser
from events.capacity import seat_holding_statuses
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from org.conduct.constants import (
    FLAG_DROPPED_UNATTRIBUTED,
    FLAG_ROLL_CALL_UNCONFIRMED,
    Outcome,
    OutcomeSource,
    Tier,
    expected_statuses,
)
from org.conduct.enforcement import tier_for_score
from org.conduct.finalize import roll_call_pending_user_ids
from org.conduct.gate import get_conduct_settings
from org.conduct.queries import user_scores
from org.conduct.scoring import forecast
from org.conduct.serializers import ForecastData, ForecastMember, SetBy, rate
from org.conduct.services import edit_block_reason
from org.conduct.sources import qualifying_ready_check
from org.contributions.serializers import MemberSummary, member_summary
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from user.querysets import with_user_profiles


class AttendanceRow(TypedDict):
    member: MemberSummary
    org_user_pk: int | None
    signup_status: str | None
    outcome: str
    source: str
    committed: bool
    virtual: bool
    finalized: bool
    voided: bool
    flag: str | None
    set_by: SetBy | None
    reason: str
    show_rate: float
    status: Literal["new", "scored"]


class AttendanceData(TypedDict):
    event_id: int
    state: str
    finalized_at: str | None
    editable: bool
    editable_reason: str | None
    rows: list[AttendanceRow]


_FORECAST_EXTRA_STATUSES: frozenset[str] = frozenset(
    {SignupStatus.WAITLISTED, SignupStatus.TENTATIVE}
)

_NO_VIRTUAL_STATES: frozenset[str] = frozenset(
    {EventState.COMPLETED, EventState.CANCELLED}
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return serializers.DateTimeField().to_representation(value)


def _set_by(user: CustomUser | None) -> SetBy | None:
    if user is None:
        return None
    return SetBy(user_pk=user.pk, username=user.username)


def _flag(
    outcome: str, user_id: int, signup_status: str | None, pending_users: set[int]
) -> str | None:
    if outcome != Outcome.PENDING:
        return None
    if signup_status == SignupStatus.DROPPED:
        return FLAG_DROPPED_UNATTRIBUTED
    if user_id in pending_users:
        return FLAG_ROLL_CALL_UNCONFIRMED
    return None


def _sort_key(row: AttendanceRow) -> tuple[str, int]:
    member = row["member"]
    return ((member["nickname"] or member["username"]).casefold(), member["user_pk"])


def event_attendance(event: Event, *, now: datetime) -> AttendanceData:
    signups = list(
        with_user_profiles(EventSignup.objects.filter(event_id=event.pk), "user")
    )
    status_by_user = {s.user_id: s.status for s in signups}
    rows = list(
        with_user_profiles(
            AttendanceOutcome.objects.filter(event_id=event.pk), "org_user__user"
        ).select_related("set_by")
    )
    with_row = {row.org_user.user_id for row in rows}

    virtual: list[EventSignup] = []
    if event.conduct_finalized_at is None and event.state not in _NO_VIRTUAL_STATES:
        expected = expected_statuses(event) | {SignupStatus.DROPPED}
        virtual = [
            s for s in signups if s.status in expected and s.user_id not in with_row
        ]
    org_users = {
        ou.user_id: ou
        for ou in with_user_profiles(
            OrgUser.objects.filter(
                organization_id=event.organization_id,
                user_id__in=[s.user_id for s in virtual],
            ),
            "user",
        )
    }

    pending_users = roll_call_pending_user_ids(
        event, signups, qualifying_ready_check(event)
    )
    user_ids = with_row | {s.user_id for s in virtual}
    scores = user_scores(
        event.organization_id,
        user_ids,
        now=now,
        settings=get_conduct_settings(event.organization_id),
    )

    result: list[AttendanceRow] = []
    for row in rows:
        user_id = row.org_user.user_id
        signup_status = (
            status_by_user.get(user_id) or row.signup_status_at_close or None
        )
        score = scores[user_id]
        result.append(
            AttendanceRow(
                member=member_summary(row.org_user),
                org_user_pk=row.org_user_id,
                signup_status=signup_status,
                outcome=row.outcome,
                source=row.source,
                committed=row.committed,
                virtual=False,
                finalized=row.finalized_at is not None,
                voided=row.voided_at is not None,
                flag=_flag(row.outcome, user_id, signup_status, pending_users),
                set_by=_set_by(row.set_by),
                reason=row.reason,
                show_rate=rate(score.show_rate),
                status=score.status,
            )
        )
    for signup in virtual:
        org_user = org_users.get(signup.user_id) or OrgUser(
            user=signup.user, organization_id=event.organization_id
        )
        score = scores[signup.user_id]
        result.append(
            AttendanceRow(
                member=member_summary(org_user),
                org_user_pk=org_user.pk,
                signup_status=signup.status,
                outcome=Outcome.PENDING.value,
                source=OutcomeSource.DEFAULT.value,
                committed=True,
                virtual=True,
                finalized=False,
                voided=False,
                flag=_flag(
                    Outcome.PENDING, signup.user_id, signup.status, pending_users
                ),
                set_by=None,
                reason="",
                show_rate=rate(score.show_rate),
                status=score.status,
            )
        )
    result.sort(key=_sort_key)

    block_reason = edit_block_reason(event)
    return AttendanceData(
        event_id=event.pk,
        state=event.state,
        finalized_at=_iso(event.conduct_finalized_at),
        editable=block_reason is None,
        editable_reason=block_reason,
        rows=result,
    )


def event_forecast(event: Event, *, now: datetime) -> ForecastData:
    seat_statuses = seat_holding_statuses(event)
    signups = list(
        EventSignup.objects.nocache()
        .filter(event_id=event.pk, status__in=seat_statuses | _FORECAST_EXTRA_STATUSES)
        .values_list("user_id", "status")
    )
    settings = get_conduct_settings(event.organization_id)
    scores = user_scores(
        event.organization_id,
        {user_id for user_id, _ in signups},
        now=now,
        settings=settings,
    )

    seat_holders = [user_id for user_id, status in signups if status in seat_statuses]
    result = forecast([scores[user_id].show_rate for user_id in seat_holders])
    members: dict[str, ForecastMember] = {}
    for user_id, status in signups:
        score = scores[user_id]
        tier = tier_for_score(score, settings)
        members[str(user_id)] = ForecastMember(
            show_rate=rate(score.show_rate),
            status=score.status,
            tier=tier.value,
            deferred=settings.back_of_line_enabled
            and status == SignupStatus.WAITLISTED
            and tier != Tier.OK,
        )

    capacity = event.max_players or None
    return ForecastData(
        seat_holders=result.seat_holders,
        expected=rate(result.expected),
        low=result.low,
        high=result.high,
        waitlisted=sum(1 for _, s in signups if s == SignupStatus.WAITLISTED),
        pending_approval=sum(
            1 for _, s in signups if s == SignupStatus.PENDING_APPROVAL
        ),
        capacity=capacity,
        expected_open_seats=(
            rate(max(0.0, capacity - result.expected)) if capacity else None
        ),
        new_members=sum(1 for u in seat_holders if scores[u].status == "new"),
        members=members,
    )
