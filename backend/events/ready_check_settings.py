from collections.abc import Callable, Mapping
from typing import Any, Final

from rest_framework import serializers

from events.models import Event
from events.ready_check_constants import READY_CHECK_FIELD_RANGES, PostCullFillMode

READY_CHECK_FIELD_KWARGS: Final[dict[str, dict[str, int]]] = {
    field: {"min_value": low, "max_value": high}
    for field, (low, high) in READY_CHECK_FIELD_RANGES.items()
}

READY_CHECK_CONFIG_FIELDS: Final[tuple[str, ...]] = (
    "ready_check_scope",
    "ready_check_open_minutes",
    "ready_check_escalation_minutes",
    "ready_check_close_minutes",
    "ready_check_chase_minutes",
    "ready_check_min_completion_pct",
    "ready_check_low_completion_action",
    "ready_check_notify_on_signup",
    "ready_check_drop_notice",
    "start_cull_enabled",
    "start_cull_minutes_after",
    "post_cull_fill_mode",
)
READY_CHECK_SETTINGS_FIELDS: Final[tuple[str, ...]] = (
    *READY_CHECK_CONFIG_FIELDS,
    "event_voice_channel_id",
    "voice_presence_confirms",
)
READY_CHECK_SNAPSHOT_FIELDS: Final[tuple[str, ...]] = (
    "roll_call_mode",
    *READY_CHECK_SETTINGS_FIELDS,
)

ROLL_CALL_RULE_FIELDS: Final[frozenset[str]] = frozenset(
    {"roll_call_enabled", "auto_confirm"}
)
TIMING_RULE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "ready_check_open_minutes",
        "ready_check_escalation_minutes",
        "ready_check_close_minutes",
        "ready_check_chase_minutes",
    }
)
VOICE_RULE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "event_voice_channel_id",
        "start_cull_enabled",
        "voice_presence_confirms",
        "post_cull_fill_mode",
    }
)

AUTO_CONFIRM_MESSAGE: Final = (
    "Auto-confirm must be off while the ready check (roll call) is on: "
    "every member has to confirm themselves."
)
CLOSE_MESSAGE: Final = (
    "The check must close after it opens "
    "(close minutes must be fewer than open minutes)."
)
ESCALATION_MESSAGE: Final = (
    "Escalation must fall between open and close, or be 0 to turn it off."
)
CHASE_MESSAGE: Final = (
    "The chase falls before the check opens: chase + close must be less than open."
)
VOICE_CHANNEL_MESSAGES: Final[dict[str, str]] = {
    "start_cull_enabled": "The start cull needs an event voice channel.",
    "voice_presence_confirms": "Voice presence confirms need an event voice channel.",
    "post_cull_fill_mode": "Filling by voice arrival needs an event voice channel.",
}

Resolver = Callable[[str], Any]


def _current_value(field: str, current: object | None) -> Any:
    if current is not None:
        return getattr(current, field)
    return Event._meta.get_field(field).get_default()


def _roll_call_errors(value: Resolver) -> dict[str, str] | None:
    if value("roll_call_enabled") and value("auto_confirm"):
        return {"auto_confirm": AUTO_CONFIRM_MESSAGE}
    return None


def _timing_errors(value: Resolver) -> dict[str, str] | None:
    open_minutes = value("ready_check_open_minutes")
    close_minutes = value("ready_check_close_minutes")
    escalation = value("ready_check_escalation_minutes")
    chase = value("ready_check_chase_minutes")
    if not open_minutes > close_minutes:
        return {"ready_check_close_minutes": CLOSE_MESSAGE}
    if escalation and not open_minutes > escalation >= close_minutes:
        return {"ready_check_escalation_minutes": ESCALATION_MESSAGE}
    if chase is not None and not chase + close_minutes < open_minutes:
        return {"ready_check_chase_minutes": CHASE_MESSAGE}
    return None


def _voice_errors(value: Resolver) -> dict[str, str] | None:
    if value("event_voice_channel_id"):
        return None
    triggers = {
        "start_cull_enabled": bool(value("start_cull_enabled")),
        "voice_presence_confirms": bool(value("voice_presence_confirms")),
        "post_cull_fill_mode": value("post_cull_fill_mode")
        == PostCullFillMode.VOICE_ARRIVAL,
    }
    for field, triggered in triggers.items():
        if triggered:
            return {field: VOICE_CHANNEL_MESSAGES[field]}
    return None


_RULE_GROUPS: Final[
    tuple[tuple[frozenset[str], Callable[[Resolver], dict[str, str] | None]], ...]
] = (
    (ROLL_CALL_RULE_FIELDS, _roll_call_errors),
    (TIMING_RULE_FIELDS, _timing_errors),
    (VOICE_RULE_FIELDS, _voice_errors),
)


def validate_ready_check_settings(
    data: Mapping[str, Any], current: object | None, *, is_create: bool
) -> None:
    def value(field: str) -> Any:
        if field in data:
            return data[field]
        return _current_value(field, current)

    run_all = is_create and current is None
    for fields, check in _RULE_GROUPS:
        touched = run_all or any(
            field in data and data[field] != _current_value(field, current)
            for field in fields
        )
        if not touched:
            continue
        errors = check(value)
        if errors:
            raise serializers.ValidationError(errors)


def ready_check_settings_snapshot(event: Event) -> dict[str, Any]:
    return {field: getattr(event, field) for field in READY_CHECK_SNAPSHOT_FIELDS}
