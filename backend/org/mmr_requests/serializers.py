from typing import Any

from django.db.models import Prefetch, QuerySet
from django.urls import reverse
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList

from app.models import CustomUser
from org.mmr_requests.permissions import can_review_mmr_request, review_flags
from org.models import MmrChangeRequest, OrgUserGameMmr
from org.models_mmr_requests import TEXT_MAX_LENGTH


def with_serializer_relations(
    qs: QuerySet[MmrChangeRequest],
) -> QuerySet[MmrChangeRequest]:
    return (
        qs.nocache()
        .select_related(
            "subject_user",
            "subject_user__base_profile",
            "requester",
            "reviewed_by",
            "organization",
            "league",
            "league__organization",
            "league_user",
            "org_user",
        )
        .prefetch_related(
            Prefetch(
                "org_user__game_mmrs",
                queryset=OrgUserGameMmr.objects.nocache(),
                to_attr="mmr_request_rows",
            )
        )
    )


class MmrChangeRequestSerializer(serializers.ModelSerializer):
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True, default=None
    )
    requester_username = serializers.CharField(
        source="requester.username", read_only=True
    )
    subject = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    league = serializers.SerializerMethodField()
    current_mmr = serializers.SerializerMethodField()
    current_verified = serializers.SerializerMethodField()
    has_screenshot = serializers.SerializerMethodField()
    screenshot_url = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = MmrChangeRequest
        fields = (
            "id",
            "target",
            "game_type",
            "status",
            "source",
            "requested_mmr",
            "approved_mmr",
            "previous_mmr",
            "previous_verified",
            "note",
            "rejection_reason",
            "reviewed_at",
            "reviewed_by_username",
            "created_at",
            "subject",
            "requester_username",
            "organization",
            "league",
            "current_mmr",
            "current_verified",
            "has_screenshot",
            "screenshot_url",
            "can_review",
        )
        read_only_fields = fields

    def _viewer(self) -> CustomUser | None:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return user

    def _can_review(self, obj: MmrChangeRequest) -> bool:
        viewer = self._viewer()
        if viewer is None:
            return False
        memo: dict[int, bool] = self.context.setdefault("_mmr_can_review", {})
        if obj.pk not in memo:
            memo[obj.pk] = can_review_mmr_request(viewer, obj)
        return memo[obj.pk]

    def _current(self, obj: MmrChangeRequest) -> tuple[int, bool]:
        if obj.target == MmrChangeRequest.Target.LEAGUE:
            lu = obj.league_user
            if lu is None:
                return 0, False
            return max(lu.mmr, 0), lu.mmr_verified_at is not None
        ou = obj.org_user
        if ou is None:
            return 0, False
        rows = getattr(ou, "mmr_request_rows", None)
        if rows is None:
            rows = list(OrgUserGameMmr.objects.nocache().filter(org_user_id=ou.pk))
            ou.mmr_request_rows = rows  # type: ignore[attr-defined]
        for row in rows:
            if row.game_type == obj.game_type:
                return row.mmr, row.verified_at is not None
        return 0, False

    def get_subject(self, obj: MmrChangeRequest) -> dict[str, Any]:
        user = obj.subject_user
        return {
            "pk": user.pk,
            "username": user.username,
            "nickname": user.nickname,
            "avatarUrl": user.avatarUrl,
        }

    def get_organization(self, obj: MmrChangeRequest) -> dict[str, Any]:
        return {"pk": obj.organization_id, "name": obj.organization.name}

    def get_league(self, obj: MmrChangeRequest) -> dict[str, Any] | None:
        if obj.league is None:
            return None
        return {"pk": obj.league_id, "name": obj.league.name}

    def get_current_mmr(self, obj: MmrChangeRequest) -> int:
        return self._current(obj)[0]

    def get_current_verified(self, obj: MmrChangeRequest) -> bool:
        return self._current(obj)[1]

    def get_has_screenshot(self, obj: MmrChangeRequest) -> bool:
        return bool(obj.screenshot.name)

    def get_screenshot_url(self, obj: MmrChangeRequest) -> str | None:
        if not obj.screenshot.name:
            return None
        viewer = self._viewer()
        if viewer is None:
            return None
        if viewer.pk != obj.subject_user_id and not self._can_review(obj):
            return None
        return reverse("mmr-request-screenshot", kwargs={"pk": obj.pk})

    def get_can_review(self, obj: MmrChangeRequest) -> bool:
        return self._can_review(obj)


def require_target_fields(attrs: dict[str, Any]) -> dict[str, Any]:
    if attrs["target"] == MmrChangeRequest.Target.LEAGUE:
        if "league_user" not in attrs:
            raise serializers.ValidationError(
                {"league_user": ["This field is required."]}
            )
    else:
        if "org_user" not in attrs:
            raise serializers.ValidationError({"org_user": ["This field is required."]})
        if "game_type" not in attrs:
            raise serializers.ValidationError(
                {"game_type": ["This field is required."]}
            )
    return attrs


class MmrRequestCreateSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=MmrChangeRequest.Target.choices)
    org_user = serializers.IntegerField(required=False, min_value=1)
    league_user = serializers.IntegerField(required=False, min_value=1)
    game_type = serializers.IntegerField(required=False)
    requested_mmr = serializers.IntegerField()
    screenshot = serializers.FileField(allow_empty_file=False)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=TEXT_MAX_LENGTH,
        default="",
        trim_whitespace=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return require_target_fields(attrs)


def serialize_requests(rows: list[MmrChangeRequest], request: Request) -> ReturnList:
    user = request.user if request.user.is_authenticated else None
    context = {"request": request, "_mmr_can_review": review_flags(user, rows)}
    return MmrChangeRequestSerializer(rows, many=True, context=context).data


def serialize_request(row: MmrChangeRequest, request: Request) -> ReturnDict:
    return MmrChangeRequestSerializer(row, context={"request": request}).data


class MmrApproveSerializer(serializers.Serializer):
    mmr = serializers.IntegerField(required=False, allow_null=True, default=None)


class MmrRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=True
    )


class MmrStaffSetSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=MmrChangeRequest.Target.choices)
    org_user = serializers.IntegerField(required=False, min_value=1)
    league_user = serializers.IntegerField(required=False, min_value=1)
    game_type = serializers.IntegerField(required=False)
    mmr = serializers.IntegerField()
    screenshot = serializers.FileField(
        required=False, allow_null=True, allow_empty_file=False, default=None
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=TEXT_MAX_LENGTH,
        default="",
        trim_whitespace=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return require_target_fields(attrs)
