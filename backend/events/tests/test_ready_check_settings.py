from datetime import time, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater, OrgEventDefaults
from events.ready_check_settings import (
    AUTO_CONFIRM_MESSAGE,
    READY_CHECK_SETTINGS_FIELDS,
)
from events.serializers import EventSlimSerializer
from events.services import generate_events_for_repeater
from events.tests.base import EventTestCase

REFERENCE_PRESET: dict[str, Any] = {
    "roll_call_enabled": True,
    "roll_call_mode": "automatic",
    "auto_confirm": False,
    "ready_check_scope": "main_and_fill",
    "ready_check_min_completion_pct": 70,
    "ready_check_low_completion_action": "non_binding",
    "ready_check_chase_minutes": 20,
    "start_cull_enabled": True,
    "start_cull_minutes_after": 1,
    "post_cull_fill_mode": "line_order",
    "event_voice_channel_id": "123456789012345678",
}

LEGACY_R1: dict[str, Any] = {"roll_call_enabled": True, "auto_confirm": True}

VALIDATION_MATRIX: tuple[tuple[str, dict[str, Any], str], ...] = (
    ("R1", LEGACY_R1, "auto_confirm"),
    (
        "R2",
        {"ready_check_open_minutes": 10, "ready_check_close_minutes": 10},
        "ready_check_close_minutes",
    ),
    (
        "R3",
        {
            "ready_check_open_minutes": 120,
            "ready_check_escalation_minutes": 130,
            "ready_check_close_minutes": 10,
        },
        "ready_check_escalation_minutes",
    ),
    (
        "R4",
        {
            "ready_check_open_minutes": 35,
            "ready_check_close_minutes": 10,
            "ready_check_chase_minutes": 30,
        },
        "ready_check_chase_minutes",
    ),
    (
        "R5 pct",
        {"ready_check_min_completion_pct": 101},
        "ready_check_min_completion_pct",
    ),
    ("R5 open", {"ready_check_open_minutes": 0}, "ready_check_open_minutes"),
    ("R5 cull", {"start_cull_minutes_after": 121}, "start_cull_minutes_after"),
    ("R6 cull", {"start_cull_enabled": True}, "start_cull_enabled"),
    ("R6 voice", {"voice_presence_confirms": True}, "voice_presence_confirms"),
    (
        "R6 fill",
        {"post_cull_fill_mode": "voice_arrival"},
        "post_cull_fill_mode",
    ),
)

ACCEPTED: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "escalation off",
        {
            "ready_check_open_minutes": 120,
            "ready_check_escalation_minutes": 0,
            "ready_check_close_minutes": 10,
        },
    ),
    (
        "chase after open",
        {
            "ready_check_open_minutes": 41,
            "ready_check_close_minutes": 10,
            "ready_check_chase_minutes": 30,
        },
    ),
)


def _writable(body: dict[str, Any], read_only: set[str]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in read_only}


@patch("events.services.notify_create_discord_event", MagicMock())
@patch("events.services.notify_new_event", MagicMock())
class ReadyCheckSettingsApiTests(EventTestCase):
    TARGETS = ("event", "series", "defaults", "one_off")

    def setUp(self) -> None:
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=30),
            created_by=self.admin,
        )
        self.defaults = OrgEventDefaults.objects.create(organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def url(self, target: str) -> str:
        if target == "event":
            return f"/api/events/{self.event.pk}/"
        if target == "series":
            return f"/api/events/repeaters/{self.repeater.pk}/"
        return f"/api/events/defaults/{self.defaults.pk}/"

    def write(self, target: str, data: dict[str, Any]) -> Response:
        if target != "one_off":
            return self.client.patch(self.url(target), data, format="json")
        return self.client.post(
            f"/api/events/repeaters/{self.repeater.pk}/create-event/",
            {"scheduled_at": (tz.now() + timedelta(days=3)).isoformat(), **data},
            format="json",
        )

    def read(self, target: str, resp: Response) -> dict[str, Any]:
        if target == "one_off":
            return self.client.get(f"/api/events/{resp.data['id']}/").data
        if target == "defaults":
            return self.client.get(
                "/api/events/defaults/", {"organization": self.org.pk}
            ).data
        return self.client.get(self.url(target)).data

    def test_round_trip(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, REFERENCE_PRESET)
                self.assertIn(resp.status_code, (200, 201), resp.data)
                body = self.read(target, resp)
                for field, value in REFERENCE_PRESET.items():
                    self.assertEqual(body[field], value, field)

    def test_chase_null_round_trip(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, {"ready_check_chase_minutes": None})
                self.assertIn(resp.status_code, (200, 201), resp.data)
                self.assertIsNone(self.read(target, resp)["ready_check_chase_minutes"])

    def test_validation_matrix(self) -> None:
        for target in self.TARGETS:
            for rule, data, key in VALIDATION_MATRIX:
                with self.subTest(target=target, rule=rule):
                    resp = self.write(target, data)
                    self.assertEqual(resp.status_code, 400, resp.data)
                    self.assertIn(key, resp.data)
                    if rule == "R1":
                        self.assertIn(
                            "every member has to confirm", str(resp.data[key][0])
                        )
                        self.assertEqual(str(resp.data[key][0]), AUTO_CONFIRM_MESSAGE)

    def test_valid_edges_accepted(self) -> None:
        for target in self.TARGETS:
            for label, data in ACCEPTED:
                with self.subTest(target=target, case=label):
                    resp = self.write(target, data)
                    self.assertIn(resp.status_code, (200, 201), resp.data)

    def test_patch_merges_instance(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(roll_call_enabled=True)
        EventRepeater.objects.filter(pk=self.repeater.pk).update(roll_call_enabled=True)
        OrgEventDefaults.objects.filter(pk=self.defaults.pk).update(
            roll_call_enabled=True
        )
        for target in ("event", "series", "defaults"):
            with self.subTest(target=target):
                resp = self.write(target, {"auto_confirm": True})
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertIn("auto_confirm", resp.data)

    def test_unrelated_patch_on_legacy_row(self) -> None:
        legacy = {"ready_check_open_minutes": 5, "ready_check_close_minutes": 10}
        Event.objects.filter(pk=self.event.pk).update(**legacy)
        EventRepeater.objects.filter(pk=self.repeater.pk).update(**legacy)
        for target in ("event", "series"):
            with self.subTest(target=target):
                resp = self.write(target, {"name": "x"})
                self.assertEqual(resp.status_code, 200, resp.data)
        OrgEventDefaults.objects.filter(pk=self.defaults.pk).update(**legacy)
        resp = self.write("defaults", {"min_players": 4})
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_full_payload_patch_on_legacy_row(self) -> None:
        # Single events reject discord_signup_reminder=True; keep that rule out of
        # a full-form save so only the ready-check rules are under test.
        Event.objects.filter(pk=self.event.pk).update(
            discord_signup_reminder=False, **LEGACY_R1
        )
        EventRepeater.objects.filter(pk=self.repeater.pk).update(**LEGACY_R1)
        read_only = {
            "event": {
                "id",
                "state",
                "contributions_awarded_at",
                "event_repeater",
                "event_repeater_name",
                "is_off_schedule",
                "tournament",
                "created_by",
                "created_at",
                "updated_at",
                "user_can_manage",
                "user_can_manage_event_staff",
            },
            "series": {
                "id",
                "created_by",
                "created_at",
                "updated_at",
                "subscriber_count",
                "is_subscribed",
                "next_event_date",
                "organization_name",
            },
        }
        for target, skip in read_only.items():
            with self.subTest(target=target):
                body = self.client.get(self.url(target)).data
                payload = {**_writable(dict(body), skip), "name": "Renamed"}
                resp = self.client.patch(self.url(target), payload, format="json")
                self.assertEqual(resp.status_code, 200, resp.data)
                self.assertTrue(resp.data["roll_call_enabled"])
                self.assertTrue(resp.data["auto_confirm"])

    def test_one_off_against_legacy_series(self) -> None:
        EventRepeater.objects.filter(pk=self.repeater.pk).update(**LEGACY_R1)
        resp = self.write("one_off", LEGACY_R1)
        self.assertEqual(resp.status_code, 201, resp.data)

        EventRepeater.objects.filter(pk=self.repeater.pk).update(
            roll_call_enabled=True, auto_confirm=False
        )
        resp = self.write("one_off", {"auto_confirm": True})
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("auto_confirm", resp.data)

    def test_series_cascade(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Daily Ready",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=1),
            generate_days_ahead=3,
            created_by=self.admin,
            **REFERENCE_PRESET,
        )
        events = generate_events_for_repeater(repeater)
        self.assertGreaterEqual(len(events), 2)
        for event in events:
            event.refresh_from_db()
            for field, value in REFERENCE_PRESET.items():
                self.assertEqual(getattr(event, field), value, field)

        off_schedule, *scheduled = events
        Event.objects.filter(pk=off_schedule.pk).update(is_off_schedule=True)
        resp = self.client.patch(
            f"/api/events/repeaters/{repeater.pk}/",
            {"ready_check_open_minutes": 90},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        for event in scheduled:
            event.refresh_from_db()
            self.assertEqual(event.state, EventState.UPCOMING)
            self.assertEqual(event.ready_check_open_minutes, 90)
        off_schedule.refresh_from_db()
        self.assertEqual(off_schedule.ready_check_open_minutes, 120)


class EventSlimReadyCheckFieldsTest(EventTestCase):
    def test_slim_exposes_settings(self) -> None:
        self.assertLessEqual(
            set(READY_CHECK_SETTINGS_FIELDS), set(EventSlimSerializer.Meta.fields)
        )

    def test_slim_settings_read_only(self) -> None:
        fields = EventSlimSerializer().fields
        for name in READY_CHECK_SETTINGS_FIELDS:
            self.assertTrue(fields[name].read_only, name)
