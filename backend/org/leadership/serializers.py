from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from org.leadership.constants import (
    REASON_MAX_LENGTH,
    SCORE_MAX,
    SCORE_MIN,
    SETTINGS_DEFAULTS,
    SETTINGS_RANGES,
)
from org.leadership.kinds import RATED_KINDS
from org.models_leadership import OrgLeadershipSettings

POINT_VALUE_MAX = 1000


def settings_data(
    row: OrgLeadershipSettings,
    points: list[dict[str, Any]],
    *,
    moderator_count: int,
) -> dict[str, Any]:
    return {
        **{field: getattr(row, field) for field in SETTINGS_DEFAULTS},
        "defaults": dict(SETTINGS_DEFAULTS),
        "ranges": {k: list(v) for k, v in SETTINGS_RANGES.items()},
        "points": points,
        "moderator_count": moderator_count,
    }


def _int_field(name: str) -> serializers.IntegerField:
    low, high = SETTINGS_RANGES[name]
    return serializers.IntegerField(required=False, min_value=low, max_value=high)


def _nullable_int_field(name: str) -> serializers.IntegerField:
    low, high = SETTINGS_RANGES[name]
    return serializers.IntegerField(
        required=False, allow_null=True, min_value=low, max_value=high
    )


def _float_field(name: str) -> serializers.FloatField:
    low, high = SETTINGS_RANGES[name]
    return serializers.FloatField(required=False, min_value=low, max_value=high)


class SettingsUpdateSerializer(serializers.Serializer):
    review_window_hours = _int_field("review_window_hours")
    rating_max_points = _int_field("rating_max_points")
    rating_min_reviewers = _int_field("rating_min_reviewers")
    ranked_min_reviews = _int_field("ranked_min_reviews")
    prior_rating = _float_field("prior_rating")
    prior_strength = _float_field("prior_strength")
    half_life_days = _int_field("half_life_days")
    max_age_days = _int_field("max_age_days")
    leaderboard_public = serializers.BooleanField(required=False)
    require_staff_release = serializers.BooleanField(required=False)
    review_dms_enabled = serializers.BooleanField(required=False)
    captain_feedback_visible = serializers.BooleanField(required=False)
    auto_release_after_hours = _nullable_int_field("auto_release_after_hours")
    points = serializers.DictField(
        child=serializers.IntegerField(
            min_value=0, max_value=POINT_VALUE_MAX, allow_null=True
        ),
        required=False,
    )

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {key: ["Unknown setting."] for key in unknown}
                )
        return super().to_internal_value(data)

    def validate_points(self, value: dict[str, int | None]) -> dict[str, int | None]:
        allowed = {k.value for k in RATED_KINDS}
        bad = sorted(set(value) - allowed)
        if bad:
            raise serializers.ValidationError(f"No point value for {bad}.")
        return value


class TraitItemSerializer(serializers.Serializer):
    key = serializers.SlugField(max_length=32)
    label = serializers.CharField(max_length=48, required=False)
    order = serializers.IntegerField(min_value=0, max_value=1000, required=False)
    active = serializers.BooleanField(required=False)


class TraitsPutSerializer(serializers.Serializer):
    traits = TraitItemSerializer(many=True)


class ReviewPutSerializer(serializers.Serializer):
    scores = serializers.DictField(
        child=serializers.IntegerField(min_value=SCORE_MIN, max_value=SCORE_MAX),
        allow_empty=False,
    )


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=REASON_MAX_LENGTH)


class ReleaseBodySerializer(serializers.Serializer):
    captains = serializers.ListField(
        child=serializers.IntegerField(),
        max_length=64,
        allow_empty=False,
        required=False,
    )
