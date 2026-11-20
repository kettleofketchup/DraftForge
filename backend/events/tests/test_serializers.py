from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from events.serializers import EventSignupSerializer, EventSlimSerializer
from events.services import process_rsvp
from events.tests.base import EventTestCase

# Fields that fire_due_reminders reads off slim payloads from get_events_list.
# If the serializer omits any of these, getattr() returns None and the fire
# path silently uses defaults. The CI test below catches the trap.
REMINDER_FIELDS_REQUIRED_BY_FIRE_PATH = [
    "discord_announcement",
    "discord_announcement_hours",
    "discord_announcement_channel_id",
    "discord_signup_reminder",
    "discord_signup_reminder_hours",
    "discord_confirm_attendance",
    "discord_confirm_attendance_hours",
    "discord_profile_reminder",
    "discord_profile_reminder_hours",
    "discord_start_mention",
    "discord_start_mention_minutes",
]


class EventSlimSerializerReminderFieldsTest(TestCase):
    def test_slim_serializer_exposes_all_reminder_fields(self):
        exposed = set(EventSlimSerializer.Meta.fields)
        missing = [f for f in REMINDER_FIELDS_REQUIRED_BY_FIRE_PATH if f not in exposed]
        self.assertEqual(missing, [], f"EventSlimSerializer missing: {missing}")


@patch("events.services.notify_signup_changed")
class EligibilityReasonsVisibilityTests(EventTestCase):
    def test_reasons_hidden_from_other_members(self, _notify: object) -> None:
        ev = self.make_event(require_steam_id=True)
        owner = self.make_user()
        process_rsvp(ev, owner)
        api = APIClient()
        expected = {
            self.make_user(): [],
            owner: ["steam_id_missing"],
            self.admin: ["steam_id_missing"],
        }
        for viewer, codes in expected.items():
            with self.subTest(viewer=viewer.username):
                api.force_authenticate(viewer)
                resp = api.get(f"/api/events/signups/?event={ev.pk}")
                self.assertEqual(resp.status_code, 200, resp.content)
                body = resp.json()
                rows = body["results"] if isinstance(body, dict) else body
                (row,) = [r for r in rows if r["user"] == owner.pk]
                self.assertEqual([r["code"] for r in row["eligibility_reasons"]], codes)

    def test_reasons_hidden_from_anonymous_and_without_request(
        self, _notify: object
    ) -> None:
        ev = self.make_event(require_steam_id=True)
        signup = process_rsvp(ev, self.make_user())
        self.assertEqual(EventSignupSerializer(signup).data["eligibility_reasons"], [])
        resp = APIClient().get(f"/api/events/signups/?event={ev.pk}")
        body = resp.json()
        rows = body["results"] if isinstance(body, dict) else body
        self.assertEqual(rows[0]["eligibility_reasons"], [])
