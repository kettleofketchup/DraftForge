from types import SimpleNamespace
from typing import Any

from django.test import SimpleTestCase
from rest_framework.serializers import ValidationError

from events.models import Event
from events.ready_check_constants import READY_CHECK_FIELD_RANGES
from events.ready_check_settings import (
    READY_CHECK_FIELD_KWARGS,
    READY_CHECK_SETTINGS_FIELDS,
    ready_check_settings_snapshot,
    validate_ready_check_settings,
)

R1_MESSAGE = (
    "Auto-confirm must be off while the ready check (roll call) is on: "
    "every member has to confirm themselves."
)
R2_MESSAGE = (
    "The check must close after it opens "
    "(close minutes must be fewer than open minutes)."
)
R3_MESSAGE = "Escalation must fall between open and close, or be 0 to turn it off."
R4_MESSAGE = (
    "The chase falls before the check opens: chase + close must be less than open."
)
VOICE_CHANNEL = "123456789012345678"

SNAPSHOT_KEYS = {
    "roll_call_mode",
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
    "event_voice_channel_id",
    "voice_presence_confirms",
}


def _current(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "roll_call_enabled": False,
        "roll_call_mode": "manual",
        "auto_confirm": False,
        "ready_check_open_minutes": 120,
        "ready_check_escalation_minutes": 30,
        "ready_check_close_minutes": 10,
        "ready_check_chase_minutes": 30,
        "start_cull_enabled": False,
        "voice_presence_confirms": False,
        "post_cull_fill_mode": "line_order",
        "event_voice_channel_id": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ValidateReadyCheckSettingsTests(SimpleTestCase):
    def assert_error(
        self,
        data: dict[str, Any],
        key: str,
        message: str,
        current: object | None = None,
        is_create: bool = True,
    ) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_ready_check_settings(data, current, is_create=is_create)
        self.assertEqual(list(ctx.exception.detail.keys()), [key])
        self.assertEqual(str(ctx.exception.detail[key]), message)

    def assert_ok(
        self,
        data: dict[str, Any],
        current: object | None = None,
        is_create: bool = True,
    ) -> None:
        validate_ready_check_settings(data, current, is_create=is_create)

    def test_defaults_pass_on_create(self) -> None:
        self.assert_ok({})

    def test_r1_roll_call_with_auto_confirm(self) -> None:
        for mode in ("automatic", "manual"):
            with self.subTest(mode=mode):
                self.assert_error(
                    {
                        "roll_call_enabled": True,
                        "auto_confirm": True,
                        "roll_call_mode": mode,
                    },
                    "auto_confirm",
                    R1_MESSAGE,
                )
        self.assert_ok({"roll_call_enabled": True, "auto_confirm": False})
        self.assert_ok({"roll_call_enabled": False, "auto_confirm": True})

    def test_r2_close_not_before_open(self) -> None:
        self.assert_error(
            {
                "ready_check_open_minutes": 10,
                "ready_check_close_minutes": 10,
                "ready_check_escalation_minutes": 0,
                "ready_check_chase_minutes": None,
            },
            "ready_check_close_minutes",
            R2_MESSAGE,
        )

    def test_r3_escalation_order(self) -> None:
        self.assert_error(
            {
                "ready_check_open_minutes": 120,
                "ready_check_escalation_minutes": 130,
                "ready_check_close_minutes": 10,
            },
            "ready_check_escalation_minutes",
            R3_MESSAGE,
        )
        self.assert_ok({"ready_check_escalation_minutes": 0})
        self.assert_ok(
            {"ready_check_escalation_minutes": 10, "ready_check_close_minutes": 10}
        )

    def test_r4_chase_before_open(self) -> None:
        self.assert_error(
            {
                "ready_check_open_minutes": 35,
                "ready_check_escalation_minutes": 0,
                "ready_check_close_minutes": 10,
                "ready_check_chase_minutes": 30,
            },
            "ready_check_chase_minutes",
            R4_MESSAGE,
        )
        self.assert_ok(
            {
                "ready_check_open_minutes": 35,
                "ready_check_escalation_minutes": 0,
                "ready_check_close_minutes": 10,
                "ready_check_chase_minutes": None,
            }
        )
        self.assert_ok(
            {
                "ready_check_open_minutes": 41,
                "ready_check_escalation_minutes": 0,
                "ready_check_close_minutes": 10,
                "ready_check_chase_minutes": 30,
            }
        )

    def test_r6_voice_triggers(self) -> None:
        triggers: list[tuple[str, Any]] = [
            ("start_cull_enabled", True),
            ("voice_presence_confirms", True),
            ("post_cull_fill_mode", "voice_arrival"),
        ]
        for field, value in triggers:
            with self.subTest(field=field):
                self.assert_error(
                    {field: value},
                    field,
                    {
                        "start_cull_enabled": "The start cull needs an event voice channel.",
                        "voice_presence_confirms": "Voice presence confirms need an event voice channel.",
                        "post_cull_fill_mode": "Filling by voice arrival needs an event voice channel.",
                    }[field],
                )
                self.assert_ok({field: value, "event_voice_channel_id": VOICE_CHANNEL})
        with self.assertRaises(ValidationError) as ctx:
            validate_ready_check_settings(
                {
                    "post_cull_fill_mode": "voice_arrival",
                    "voice_presence_confirms": True,
                    "start_cull_enabled": True,
                },
                None,
                is_create=True,
            )
        self.assertEqual(list(ctx.exception.detail.keys()), ["start_cull_enabled"])
        with self.assertRaises(ValidationError) as ctx:
            validate_ready_check_settings(
                {
                    "post_cull_fill_mode": "voice_arrival",
                    "voice_presence_confirms": True,
                },
                None,
                is_create=True,
            )
        self.assertEqual(list(ctx.exception.detail.keys()), ["voice_presence_confirms"])

    def test_merges_current_values(self) -> None:
        self.assert_error(
            {"auto_confirm": True},
            "auto_confirm",
            R1_MESSAGE,
            current=_current(roll_call_enabled=True),
            is_create=False,
        )

    def test_untouched_group_skipped(self) -> None:
        current = _current(
            roll_call_enabled=True,
            auto_confirm=True,
            ready_check_open_minutes=5,
            ready_check_close_minutes=10,
        )
        self.assert_ok(
            {
                "name": "Renamed",
                "roll_call_enabled": True,
                "auto_confirm": True,
                "ready_check_open_minutes": 5,
                "ready_check_close_minutes": 10,
            },
            current=current,
            is_create=False,
        )

    def test_changed_field_runs_its_group_only(self) -> None:
        current = _current(ready_check_open_minutes=5, ready_check_close_minutes=10)
        self.assert_ok(
            {"roll_call_enabled": True, "auto_confirm": False},
            current=current,
            is_create=False,
        )

    def test_update_without_current_uses_model_defaults(self) -> None:
        self.assert_error(
            {"ready_check_close_minutes": 120},
            "ready_check_close_minutes",
            R2_MESSAGE,
            is_create=False,
        )


class ReadyCheckSettingsHelpersTests(SimpleTestCase):
    def test_snapshot_keys(self) -> None:
        event = Event(
            roll_call_mode="automatic",
            ready_check_scope="main_and_fill",
            ready_check_open_minutes=90,
            ready_check_chase_minutes=None,
            start_cull_enabled=True,
            event_voice_channel_id=VOICE_CHANNEL,
            voice_presence_confirms=True,
        )
        snapshot = ready_check_settings_snapshot(event)
        self.assertEqual(set(snapshot), SNAPSHOT_KEYS)
        for key, value in snapshot.items():
            self.assertEqual(value, getattr(event, key), key)

    def test_settings_fields(self) -> None:
        self.assertEqual(len(READY_CHECK_SETTINGS_FIELDS), 14)
        self.assertEqual(
            set(READY_CHECK_SETTINGS_FIELDS), SNAPSHOT_KEYS - {"roll_call_mode"}
        )

    def test_field_kwargs_match_ranges(self) -> None:
        self.assertEqual(set(READY_CHECK_FIELD_KWARGS), set(READY_CHECK_FIELD_RANGES))
        for field, (low, high) in READY_CHECK_FIELD_RANGES.items():
            self.assertEqual(
                READY_CHECK_FIELD_KWARGS[field], {"min_value": low, "max_value": high}
            )
