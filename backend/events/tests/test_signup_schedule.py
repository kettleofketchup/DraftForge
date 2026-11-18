"""When signups open: the per-config open policy and its propagation."""

from datetime import date, datetime, time, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from events.constants import EventState, RepeatFrequency, SignupOpenMode
from events.models import Event, EventRepeater, OrgEventDefaults
from events.signup_schedule import (
    MAX_SIGNUPS_OPEN_HOURS_BEFORE,
    compute_signups_open_at,
)
from events.tasks import open_scheduled_signups
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.base import EventTestCase


def _cfg(mode: str, hours: int = 72) -> EventRepeater:
    return EventRepeater(signup_open_mode=mode, signups_open_hours_before=hours)


class ComputeSignupsOpenAtTests(EventTestCase):
    def test_compute_modes(self) -> None:
        now = tz.now()
        at = now + timedelta(days=5)
        self.assertIsNone(compute_signups_open_at(_cfg(SignupOpenMode.MANUAL), at, now))
        self.assertEqual(
            compute_signups_open_at(_cfg(SignupOpenMode.IMMEDIATE), at, now), now
        )
        self.assertEqual(
            compute_signups_open_at(_cfg(SignupOpenMode.SCHEDULED, 48), at, now),
            at - timedelta(hours=48),
        )
        self.assertEqual(
            compute_signups_open_at(_cfg(SignupOpenMode.SCHEDULED, 0), at, now), at
        )
        past = compute_signups_open_at(
            _cfg(SignupOpenMode.SCHEDULED, 48), now + timedelta(hours=1), now
        )
        assert past is not None
        self.assertLess(past, now)


class _ApiCase(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _post_event(self, **body: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "organization": self.org.pk,
            "name": "Policy Event",
            "scheduled_at": (tz.now() + timedelta(days=5)).isoformat(),
            **body,
        }
        resp = self.client.post("/api/events/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()


class SingleEventPolicyTests(_ApiCase):
    def test_single_event_from_org_defaults(self) -> None:
        OrgEventDefaults.objects.create(
            organization=self.org,
            signup_open_mode=SignupOpenMode.SCHEDULED,
            signups_open_hours_before=48,
        )
        at = tz.now() + timedelta(days=5)
        data = self._post_event(scheduled_at=at.isoformat())
        event = Event.objects.nocache().get(pk=data["id"])
        self.assertEqual(event.signup_open_mode, SignupOpenMode.SCHEDULED)
        self.assertEqual(event.signups_open_hours_before, 48)
        self.assertEqual(event.signups_open_at, at - timedelta(hours=48))

    def test_request_policy_beats_org_defaults(self) -> None:
        OrgEventDefaults.objects.create(
            organization=self.org,
            signup_open_mode=SignupOpenMode.SCHEDULED,
            signups_open_hours_before=48,
        )
        data = self._post_event(signup_open_mode=SignupOpenMode.MANUAL)
        event = Event.objects.nocache().get(pk=data["id"])
        self.assertEqual(event.signup_open_mode, SignupOpenMode.MANUAL)
        self.assertIsNone(event.signups_open_at)

    def test_no_defaults_is_manual(self) -> None:
        data = self._post_event()
        event = Event.objects.nocache().get(pk=data["id"])
        self.assertEqual(event.signup_open_mode, SignupOpenMode.MANUAL)
        self.assertIsNone(event.signups_open_at)

    def test_reschedule_recomputes_while_upcoming(self) -> None:
        data = self._post_event(
            signup_open_mode=SignupOpenMode.SCHEDULED, signups_open_hours_before=24
        )
        new_at = tz.now() + timedelta(days=9)
        resp = self.client.patch(
            f"/api/events/{data['id']}/",
            {"scheduled_at": new_at.isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        event = Event.objects.nocache().get(pk=data["id"])
        self.assertEqual(event.signups_open_at, new_at - timedelta(hours=24))

        resp = self.client.patch(
            f"/api/events/{data['id']}/",
            {"signups_open_hours_before": 12},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        event.refresh_from_db()
        self.assertEqual(event.signups_open_at, new_at - timedelta(hours=12))

    def test_no_recompute_once_signups_open(self) -> None:
        data = self._post_event(
            signup_open_mode=SignupOpenMode.SCHEDULED, signups_open_hours_before=24
        )
        Event.objects.filter(pk=data["id"]).update(state=EventState.SIGNUPS_OPEN)
        before = Event.objects.nocache().get(pk=data["id"]).signups_open_at
        resp = self.client.patch(
            f"/api/events/{data['id']}/",
            {"signups_open_hours_before": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            Event.objects.nocache().get(pk=data["id"]).signups_open_at, before
        )

    def test_unrelated_patch_keeps_signups_open_at(self) -> None:
        data = self._post_event(
            signup_open_mode=SignupOpenMode.SCHEDULED, signups_open_hours_before=24
        )
        hand_set = tz.now() + timedelta(days=1, minutes=17)
        Event.objects.filter(pk=data["id"]).update(signups_open_at=hand_set)
        resp = self.client.patch(
            f"/api/events/{data['id']}/", {"description": "new"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            Event.objects.nocache().get(pk=data["id"]).signups_open_at, hand_set
        )

    def test_manual_reschedule_keeps_legacy_open_time(self) -> None:
        event = self.make_event(
            state=EventState.UPCOMING,
            signups_open_at=tz.now() + timedelta(days=2),
        )
        legacy = event.signups_open_at
        resp = self.client.patch(
            f"/api/events/{event.pk}/",
            {"scheduled_at": (tz.now() + timedelta(days=8)).isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        event.refresh_from_db()
        self.assertEqual(event.signups_open_at, legacy)

    def test_legacy_explicit_signups_open_at(self) -> None:
        at = tz.now() + timedelta(days=5)
        sent = at - timedelta(hours=47, minutes=40)
        data = self._post_event(
            scheduled_at=at.isoformat(), signups_open_at=sent.isoformat()
        )
        event = Event.objects.nocache().get(pk=data["id"])
        self.assertEqual(event.signup_open_mode, SignupOpenMode.SCHEDULED)
        self.assertEqual(event.signups_open_hours_before, 48)
        self.assertEqual(event.signups_open_at, sent)

    def test_hours_upper_bound(self) -> None:
        too_many = MAX_SIGNUPS_OPEN_HOURS_BEFORE + 1
        resp = self.client.post(
            "/api/events/",
            {
                "organization": self.org.pk,
                "name": "Too Early",
                "scheduled_at": (tz.now() + timedelta(days=5)).isoformat(),
                "signup_open_mode": SignupOpenMode.SCHEDULED,
                "signups_open_hours_before": too_many,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("signups_open_hours_before", resp.json())

        repeater = _make_repeater(self)
        resp = self.client.patch(
            f"/api/events/repeaters/{repeater.pk}/",
            {"signups_open_hours_before": too_many},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("signups_open_hours_before", resp.json())

        defaults = self.client.get(
            "/api/events/defaults/", {"organization": self.org.pk}
        ).json()
        resp = self.client.patch(
            f"/api/events/defaults/{defaults['id']}/",
            {"signups_open_hours_before": too_many},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("signups_open_hours_before", resp.json())

    def test_round_trip_all_three_serializers(self) -> None:
        body = {
            "signup_open_mode": SignupOpenMode.SCHEDULED,
            "signups_open_hours_before": 36,
        }
        data = self._post_event(**body)
        got = self.client.get(f"/api/events/{data['id']}/").json()
        self.assertEqual(
            (got["signup_open_mode"], got["signups_open_hours_before"]),
            ("scheduled", 36),
        )

        repeater = _make_repeater(self)
        resp = self.client.patch(
            f"/api/events/repeaters/{repeater.pk}/", body, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        got = self.client.get(f"/api/events/repeaters/{repeater.pk}/").json()
        self.assertEqual(
            (got["signup_open_mode"], got["signups_open_hours_before"]),
            ("scheduled", 36),
        )

        defaults = self.client.get(
            "/api/events/defaults/", {"organization": self.org.pk}
        ).json()
        resp = self.client.patch(
            f"/api/events/defaults/{defaults['id']}/", body, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        got = self.client.get(
            "/api/events/defaults/", {"organization": self.org.pk}
        ).json()
        self.assertEqual(
            (got["signup_open_mode"], got["signups_open_hours_before"]),
            ("scheduled", 36),
        )


def _make_repeater(case: EventTestCase, **kwargs: Any) -> EventRepeater:
    fields: dict[str, Any] = {
        "organization": case.org,
        "name": "Policy Series",
        "frequency": RepeatFrequency.WEEKLY,
        "day_of_week": 0,
        "time_of_day": time(18, 0),
        "starts_at": tz.now().date(),
        "created_by": case.admin,
        "is_active": False,
    }
    fields.update(kwargs)
    return EventRepeater.objects.create(**fields)


@patch("events.services.notify_create_discord_event", MagicMock())
@patch("events.services.notify_new_event", MagicMock())
class RepeaterPolicyCascadeTests(_ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.repeater = _make_repeater(
            self,
            signup_open_mode=SignupOpenMode.SCHEDULED,
            signups_open_hours_before=48,
        )
        self.at = tz.now() + timedelta(days=4)
        self.hand_set = tz.now() + timedelta(hours=5)
        self.upcoming = self._series_event(self.at, signups_open_at=self.hand_set)
        self.open = self._series_event(
            self.at + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            signups_open_at=self.hand_set,
        )
        self.one_off = self._series_event(
            self.at + timedelta(hours=3),
            is_off_schedule=True,
            signups_open_at=self.hand_set,
        )

    def _series_event(self, at: datetime, **kwargs: Any) -> Event:
        fields: dict[str, Any] = {
            "organization": self.org,
            "event_repeater": self.repeater,
            "name": "Policy Series",
            "scheduled_at": at,
            "state": EventState.UPCOMING,
            "signup_open_mode": SignupOpenMode.SCHEDULED,
            "signups_open_hours_before": 48,
        }
        fields.update(kwargs)
        return Event.objects.create(**fields)

    def _patch(self, body: dict[str, Any]) -> None:
        resp = self.client.patch(
            f"/api/events/repeaters/{self.repeater.pk}/", body, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        for event in (self.upcoming, self.open, self.one_off):
            event.refresh_from_db()

    def test_description_patch_keeps_hand_set_open_time(self) -> None:
        self._patch({"description": "only the blurb"})
        self.assertEqual(self.upcoming.signups_open_at, self.hand_set)

    def test_cascade_recomputes_only_on_policy_change(self) -> None:
        self._patch({"signups_open_hours_before": 24})
        self.assertEqual(self.upcoming.signups_open_at, self.at - timedelta(hours=24))
        self.assertEqual(self.upcoming.signups_open_hours_before, 24)
        self.assertEqual(self.open.signups_open_at, self.hand_set)
        self.assertEqual(self.one_off.signups_open_at, self.hand_set)

    def test_manual_cascade_never_touches(self) -> None:
        self._patch({"signup_open_mode": SignupOpenMode.MANUAL})
        self.assertEqual(self.upcoming.signups_open_at, self.hand_set)
        self._patch({"description": "edited"})
        self.assertEqual(self.upcoming.signups_open_at, self.hand_set)


@patch("events.services.notify_create_discord_event", MagicMock())
@patch("events.services.notify_new_event", MagicMock())
@patch("events.services.ensure_discord_event", MagicMock())
class OpenScheduledSignupsTests(DiscordTestMixin, EventTestCase):
    def test_open_scheduled_signups_opens_generated_event(self) -> None:
        from events.services import generate_events_for_repeater

        now = tz.now()
        soon = now + timedelta(hours=1)
        later = now + timedelta(hours=72)
        repeater = _make_repeater(
            self,
            frequency=RepeatFrequency.DAILY,
            day_of_week=None,
            time_of_day=time(0, 0),
            timezone="UTC",
            is_active=True,
            generate_days_ahead=1,
            signup_open_mode=SignupOpenMode.SCHEDULED,
            signups_open_hours_before=48,
        )
        occurrences = [soon, later]
        with (
            patch("events.services._get_next_occurrences", return_value=occurrences),
            patch("events.services._today", return_value=date.today()),
        ):
            created = generate_events_for_repeater(repeater)
        self.assertEqual(len(created), 2)

        open_scheduled_signups()

        due = Event.objects.nocache().get(event_repeater=repeater, scheduled_at=soon)
        not_due = Event.objects.nocache().get(
            event_repeater=repeater, scheduled_at=later
        )
        self.assertEqual(due.state, EventState.SIGNUPS_OPEN)
        self.assertEqual(not_due.state, EventState.UPCOMING)
