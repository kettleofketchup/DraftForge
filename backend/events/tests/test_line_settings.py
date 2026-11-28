from datetime import time, timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from events.capacity import count_seats, has_free_seat, with_signup_counts
from events.constants import RepeatFrequency, SignupStatus
from events.models import Event, EventRepeater, EventSignup, OrgEventDefaults
from events.tests.base import EventTestCase

LINE_FIELDS: tuple[str, ...] = ("line_withdraw_forfeits", "line_switch_restamps")
OFF: dict[str, bool] = {name: False for name in LINE_FIELDS}


@patch("events.services.notify_create_discord_event", MagicMock())
@patch("events.services.notify_new_event", MagicMock())
class LineSettingsTests(EventTestCase):
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

    def assert_line_fields(self, data: dict[str, object], expected: bool) -> None:
        for name in LINE_FIELDS:
            self.assertIs(data[name], expected, name)

    def test_defaults_true_on_event_repeater_org_defaults(self) -> None:
        for obj in (self.make_event(), self.repeater, self.defaults):
            obj.refresh_from_db()
            for name in LINE_FIELDS:
                self.assertIs(getattr(obj, name), True, f"{type(obj).__name__}.{name}")

    def test_event_patch_round_trip(self) -> None:
        url = f"/api/events/{self.event.pk}/"
        resp = self.client.patch(url, OFF, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assert_line_fields(self.client.get(url).data, False)

    def test_repeater_patch_round_trip(self) -> None:
        url = f"/api/events/repeaters/{self.repeater.pk}/"
        resp = self.client.patch(url, OFF, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assert_line_fields(self.client.get(url).data, False)

    def test_org_defaults_patch_round_trip(self) -> None:
        resp = self.client.patch(
            f"/api/events/defaults/{self.defaults.pk}/", OFF, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        data = self.client.get(
            "/api/events/defaults/", {"organization": self.org.pk}
        ).data
        self.assert_line_fields(data, False)

    def test_member_patch_refused(self) -> None:
        member = APIClient()
        member.force_authenticate(self.make_user())
        resp = member.patch(f"/api/events/{self.event.pk}/", OFF, format="json")
        self.assertEqual(resp.status_code, 403)
        self.event.refresh_from_db()
        for name in LINE_FIELDS:
            self.assertIs(getattr(self.event, name), True, name)

    def test_tentative_never_holds_seat(self) -> None:
        event = self.make_event(max_players=1)
        EventSignup.objects.create(
            event=event, user=self.make_user(), status=SignupStatus.TENTATIVE
        )
        self.assertEqual(count_seats(event), 0)
        self.assertTrue(has_free_seat(event))
        annotated = with_signup_counts(Event.objects.filter(pk=event.pk)).get()
        self.assertEqual(annotated.signup_count, 0)
