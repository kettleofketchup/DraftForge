from collections.abc import Mapping
from decimal import Decimal
from typing import Any, TypedDict, cast

from rest_framework import serializers

from org.conduct.constants import SETTINGS_RANGES
from org.conduct.services import EDITABLE_SETTINGS_FIELDS
from org.models_conduct import OrgConductSettings

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
