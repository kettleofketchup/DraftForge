"""Whitelisted form values a Discord preview may override."""

from typing import Any
from zoneinfo import available_timezones

from rest_framework import serializers

from events.models import Event, EventRepeater
from events.services import DISCORD_CONFIG_FIELDS
from events.signup_schedule import SIGNUP_OPEN_POLICY_FIELDS

MAX_ROLE_IDS = 25
ROLE_ID_FIELDS: tuple[str, ...] = (
    "discord_signup_role_ids",
    "discord_announcement_role_ids",
)

PREVIEW_EVENT_FIELDS: list[str] = [
    *DISCORD_CONFIG_FIELDS,
    "name",
    "description",
    "scheduled_at",
    "ends_at",
    "timezone",
    "max_players",
    "allow_user_signups",
    "game_type",
    "require_steam_id",
    "require_mmr_verified",
    "require_profile_complete",
    *SIGNUP_OPEN_POLICY_FIELDS,
]

PREVIEW_REPEATER_FIELDS: list[str] = [
    *(f for f in PREVIEW_EVENT_FIELDS if f not in ("scheduled_at", "ends_at")),
    "frequency",
    "day_of_week",
    "time_of_day",
    "starts_at",
    "ends_at",
    "is_active",
    "generate_days_ahead",
    "discord_notify_new_events",
]


def _validate_timezone(value: str) -> str:
    if value and value not in available_timezones():
        raise serializers.ValidationError("Unknown timezone.")
    return value


def _validate_role_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError("Expected a list of role ids.")
    if len(value) > MAX_ROLE_IDS:
        raise serializers.ValidationError(f"At most {MAX_ROLE_IDS} role ids.")
    ids: list[str] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, str)):
            raise serializers.ValidationError("Role ids must be numeric.")
        text = str(item)
        if not text.isdigit():
            raise serializers.ValidationError("Role ids must be numeric.")
        ids.append(text)
    return ids


class _PreviewValuesMixin(serializers.ModelSerializer):
    def validate_timezone(self, value: str) -> str:
        return _validate_timezone(value)

    def validate_discord_signup_role_ids(self, value: Any) -> list[str]:
        return _validate_role_ids(value)

    def validate_discord_announcement_role_ids(self, value: Any) -> list[str]:
        return _validate_role_ids(value)


class DiscordPreviewValuesSerializer(_PreviewValuesMixin):
    class Meta:
        model = Event
        fields = PREVIEW_EVENT_FIELDS
        validators: list[Any] = []


class DiscordPreviewRepeaterValuesSerializer(_PreviewValuesMixin):
    class Meta:
        model = EventRepeater
        fields = PREVIEW_REPEATER_FIELDS
        validators: list[Any] = []
