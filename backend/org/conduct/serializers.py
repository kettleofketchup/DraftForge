from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, Final, Literal, NotRequired, TypedDict, cast

from rest_framework import serializers

from org.conduct.constants import COUNTED, SETTINGS_RANGES
from org.conduct.scoring import MemberScore, recency_weight
from org.conduct.services import EDITABLE_SETTINGS_FIELDS
from org.contributions.serializers import MemberSummary, member_summary
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings

DEFAULT_HISTORY_LIMIT: Final[int] = 50
MAX_HISTORY_LIMIT: Final[int] = 200
RATE_DIGITS: Final[int] = 3

SettingValue = float | int | bool


class ConductSettingsData(TypedDict):
    late_cancel_hours: int
    late_cancel_weight: float
    half_life_days: int
    max_age_days: int
    prior_show_rate: float
    prior_strength: float
    min_events: int
    leaderboard_public: bool
    back_of_line_enabled: bool
    back_of_line_below: float
    require_approval_enabled: bool
    require_approval_below: float
    block_enabled: bool
    block_below: float
    enforce_on_new_members: bool
    defaults: dict[str, SettingValue]


def _plain(value: object) -> SettingValue:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool | int | float):
        return value
    raise TypeError(f"unexpected setting value {value!r}")


def _defaults() -> dict[str, SettingValue]:
    return {
        field: _plain(OrgConductSettings._meta.get_field(field).get_default())
        for field in EDITABLE_SETTINGS_FIELDS
    }


def settings_data(row: OrgConductSettings) -> ConductSettingsData:
    values: dict[str, object] = {
        field: _plain(getattr(row, field)) for field in EDITABLE_SETTINGS_FIELDS
    }
    values["defaults"] = _defaults()
    return cast(ConductSettingsData, values)


def _int_field(name: str) -> serializers.IntegerField:
    low, high = SETTINGS_RANGES[name]
    return serializers.IntegerField(required=False, min_value=low, max_value=high)


def _decimal_field(name: str, max_digits: int = 3) -> serializers.DecimalField:
    low, high = SETTINGS_RANGES[name]
    return serializers.DecimalField(
        required=False,
        max_digits=max_digits,
        decimal_places=2,
        min_value=low,
        max_value=high,
    )


class ConductSettingsUpdateSerializer(serializers.Serializer):
    late_cancel_hours = _int_field("late_cancel_hours")
    late_cancel_weight = _decimal_field("late_cancel_weight")
    half_life_days = _int_field("half_life_days")
    max_age_days = _int_field("max_age_days")
    prior_show_rate = _decimal_field("prior_show_rate")
    prior_strength = _decimal_field("prior_strength", max_digits=4)
    min_events = _int_field("min_events")
    leaderboard_public = serializers.BooleanField(required=False)
    back_of_line_enabled = serializers.BooleanField(required=False)
    back_of_line_below = _decimal_field("back_of_line_below")
    require_approval_enabled = serializers.BooleanField(required=False)
    require_approval_below = _decimal_field("require_approval_below")
    block_enabled = serializers.BooleanField(required=False)
    block_below = _decimal_field("block_below")
    enforce_on_new_members = serializers.BooleanField(required=False)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {key: ["Unknown setting."] for key in unknown}
                )
        return super().to_internal_value(data)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        current: OrgConductSettings = self.context["current"]
        half_life = attrs.get("half_life_days", current.half_life_days)
        max_age = attrs.get("max_age_days", current.max_age_days)
        if max_age < half_life:
            key = "max_age_days" if "max_age_days" in attrs else "half_life_days"
            raise serializers.ValidationError(
                {
                    key: (
                        f"Max age ({max_age} days) must be at least "
                        f"the half-life ({half_life} days)."
                    )
                }
            )
        return attrs


class LeaderboardRow(TypedDict):
    member: MemberSummary
    show_rate: float
    counted_events: int
    rank: int


class NewMemberRow(TypedDict):
    member: MemberSummary
    counted_events: int


class OwnRow(TypedDict):
    member: MemberSummary
    show_rate: float
    counted_events: int
    status: Literal["new", "scored"]
    rank: int | None


class SetBy(TypedDict):
    user_pk: int
    username: str


class HistoryItem(TypedDict):
    event_id: int | None
    event_name: str
    event_starts_at: str
    outcome: str
    source: str
    committed: bool
    finalized: bool
    voided: bool
    weight: float
    reason: NotRequired[str]
    set_by: NotRequired[SetBy | None]


def rate(value: float) -> float:
    return round(value, RATE_DIGITS)


def leaderboard_row(org_user: OrgUser, score: MemberScore, rank: int) -> LeaderboardRow:
    return LeaderboardRow(
        member=member_summary(org_user),
        show_rate=rate(score.show_rate),
        counted_events=score.counted_events,
        rank=rank,
    )


def new_member_row(org_user: OrgUser, score: MemberScore) -> NewMemberRow:
    return NewMemberRow(
        member=member_summary(org_user), counted_events=score.counted_events
    )


def own_row(org_user: OrgUser, score: MemberScore, rank: int | None) -> OwnRow:
    return OwnRow(
        member=member_summary(org_user),
        show_rate=rate(score.show_rate),
        counted_events=score.counted_events,
        status=score.status,
        rank=rank,
    )


def is_counted(row: AttendanceOutcome) -> bool:
    return (
        row.finalized_at is not None
        and row.voided_at is None
        and row.committed
        and row.outcome in COUNTED
    )


def history_item(
    row: AttendanceOutcome,
    *,
    now: datetime,
    cutoff: datetime,
    half_life_days: int,
    with_reason: bool,
) -> HistoryItem:
    weight = (
        recency_weight(row.event_starts_at, now, half_life_days)
        if is_counted(row) and row.event_starts_at >= cutoff
        else 0.0
    )
    item = HistoryItem(
        event_id=row.event_id,
        event_name=row.event_name,
        event_starts_at=serializers.DateTimeField().to_representation(
            row.event_starts_at
        ),
        outcome=row.outcome,
        source=row.source,
        committed=row.committed,
        finalized=row.finalized_at is not None,
        voided=row.voided_at is not None,
        weight=rate(weight),
    )
    if with_reason:
        set_by = row.set_by
        item["reason"] = row.reason
        item["set_by"] = (
            SetBy(user_pk=set_by.pk, username=set_by.username)
            if set_by is not None
            else None
        )
    return item


class HistoryQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        required=False,
        default=DEFAULT_HISTORY_LIMIT,
        min_value=1,
        max_value=MAX_HISTORY_LIMIT,
    )
    offset = serializers.IntegerField(required=False, default=0, min_value=0)
