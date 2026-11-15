from typing import Any, TypedDict

from rest_framework import serializers

from org.contributions.kinds import ContributionKind
from org.contributions.services import (
    MANUAL_MAX_POINTS,
    MANUAL_MIN_POINTS,
    POINT_VALUE_MAX,
    REASON_MAX_LENGTH,
)
from org.models import ContributionEntry, OrgUser

MAX_PAGE_LIMIT = 500
DEFAULT_PAGE_LIMIT = 100


class MemberSummary(TypedDict):
    org_user_pk: int
    user_pk: int
    username: str
    nickname: str | None
    avatarUrl: str | None


class EventRef(TypedDict):
    id: int
    name: str


def member_summary(org_user: OrgUser) -> MemberSummary:
    user = org_user.user
    return MemberSummary(
        org_user_pk=org_user.pk,
        user_pk=user.pk,
        username=user.username,
        nickname=user.nickname,
        avatarUrl=user.avatarUrl,
    )


def entry_data(entry: ContributionEntry, *, with_reason: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pk": entry.pk,
        "kind": entry.kind,
        "points": entry.points,
        "event": (
            EventRef(id=entry.event.pk, name=entry.event.name)
            if entry.event is not None
            else None
        ),
        "event_name": entry.event_name,
        "occurred_at": serializers.DateTimeField().to_representation(entry.occurred_at),
    }
    if with_reason:
        data["reason"] = entry.reason
    return data


def admin_entry_data(entry: ContributionEntry) -> dict[str, Any]:
    awarded_by = entry.awarded_by
    return {
        **entry_data(entry, with_reason=True),
        "member": member_summary(entry.org_user),
        "awarded_by": (
            {"pk": awarded_by.pk, "username": awarded_by.username}
            if awarded_by is not None
            else None
        ),
    }


class PeriodQuerySerializer(serializers.Serializer):
    period = serializers.CharField(required=False, allow_blank=False)


class PointValueUpdateSerializer(serializers.Serializer):
    points = serializers.IntegerField(
        allow_null=True, min_value=0, max_value=POINT_VALUE_MAX
    )
    apply_to_past = serializers.BooleanField(required=False, default=False)
    since = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("since") is not None and not attrs.get("apply_to_past"):
            raise serializers.ValidationError({"since": "since requires apply_to_past"})
        return attrs


class EntriesQuerySerializer(PeriodQuerySerializer):
    kind = serializers.ChoiceField(choices=ContributionKind.choices, required=False)
    member = serializers.IntegerField(required=False, min_value=1)
    limit = serializers.IntegerField(
        required=False,
        default=DEFAULT_PAGE_LIMIT,
        min_value=1,
        max_value=MAX_PAGE_LIMIT,
    )
    offset = serializers.IntegerField(required=False, default=0, min_value=0)


class ManualAwardCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    points = serializers.IntegerField(
        min_value=MANUAL_MIN_POINTS, max_value=MANUAL_MAX_POINTS
    )
    reason = serializers.CharField(max_length=REASON_MAX_LENGTH)
    date = serializers.DateField()
    event_id = serializers.IntegerField(required=False, allow_null=True)


class ManualAwardUpdateSerializer(serializers.Serializer):
    points = serializers.IntegerField(
        required=False, min_value=MANUAL_MIN_POINTS, max_value=MANUAL_MAX_POINTS
    )
    reason = serializers.CharField(required=False, max_length=REASON_MAX_LENGTH)
    date = serializers.DateField(required=False)
    event_id = serializers.IntegerField(required=False, allow_null=True)
