from datetime import time, timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import Tournament
from events.admission import SELF_SERVE_DISABLED_MESSAGE
from events.constants import EventState, RepeatFrequency, SignupStatus
from events.models import Event, EventRepeater, EventSignup
from events.services import (
    create_tentative_signup,
    decline_signup,
    generate_events_for_repeater,
    process_rsvp,
    staff_add_signup,
)
from events.signup_window import user_signups_open_tournament_ids
from events.tests.base import EventTestCase
from tests.cache import flush_run_cache

LIST_URL = "/api/tournaments-list/?open_signups=1"


class SelfServeAdmissionTests(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.closed = self.make_event(allow_user_signups=False)
        self.player = self.make_user()

    def test_process_rsvp_refused_when_self_serve_off(self) -> None:
        with self.assertRaisesMessage(ValueError, SELF_SERVE_DISABLED_MESSAGE):
            process_rsvp(self.closed, self.player)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_tentative_refused(self) -> None:
        with self.assertRaisesMessage(ValueError, SELF_SERVE_DISABLED_MESSAGE):
            create_tentative_signup(self.closed, self.player)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_wrong_state_keeps_existing_message(self) -> None:
        upcoming = self.make_event(state=EventState.UPCOMING)
        with self.assertRaisesMessage(ValueError, "Event is not accepting signups."):
            process_rsvp(upcoming, self.player)

    def test_decline_allowed(self) -> None:
        signup = decline_signup(self.closed, self.player)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

    def test_staff_add_allowed(self) -> None:
        signup = staff_add_signup(self.closed, self.player)
        self.assertEqual(signup.event_id, self.closed.pk)
        self.assertNotEqual(signup.status, SignupStatus.CANCELLED)

    def test_web_signup_400(self) -> None:
        self.client.force_authenticate(user=self.player)
        for intent in ("rsvp", "tentative"):
            with self.subTest(intent=intent):
                resp = self.client.post(
                    f"/api/events/{self.closed.pk}/signup/",
                    {"intent": intent},
                    format="json",
                )
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(resp.json()["error"], SELF_SERVE_DISABLED_MESSAGE)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_listing_excludes(self) -> None:
        flush_run_cache()
        tournament = Tournament.objects.create(
            name="Admission Cup", date_played=tz.now() + timedelta(days=3)
        )
        self.closed.tournament = tournament
        self.closed.save()
        self.assertNotIn(tournament.pk, user_signups_open_tournament_ids())
        listed = {row["pk"] for row in self.client.get(LIST_URL).json()}
        self.assertNotIn(tournament.pk, listed)

        self.closed.allow_user_signups = True
        self.closed.save()
        self.assertIn(tournament.pk, user_signups_open_tournament_ids())
        listed = {row["pk"] for row in self.client.get(LIST_URL).json()}
        self.assertIn(tournament.pk, listed)

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_generated_event_inherits_flag(
        self, _notify: MagicMock, _create: MagicMock
    ) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Closed Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
            allow_user_signups=False,
        )
        created = generate_events_for_repeater(repeater)
        self.assertTrue(created)
        event = created[0]
        event.transition_state(EventState.SIGNUPS_OPEN)
        event.refresh_from_db()
        with self.assertRaisesMessage(ValueError, SELF_SERVE_DISABLED_MESSAGE):
            process_rsvp(event, self.player)

    def test_org_defaults_flag_propagates(self) -> None:
        self.client.force_authenticate(user=self.admin)
        defaults = self.client.get(
            "/api/events/defaults/", {"organization": self.org.pk}
        ).json()
        resp = self.client.patch(
            f"/api/events/defaults/{defaults['id']}/",
            {"allow_user_signups": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        defaults = self.client.get(
            "/api/events/defaults/", {"organization": self.org.pk}
        ).json()
        self.assertFalse(defaults["allow_user_signups"])

        resp = self.client.post(
            "/api/events/",
            {
                "organization": self.org.pk,
                "name": "From Defaults",
                "scheduled_at": (tz.now() + timedelta(days=5)).isoformat(),
                "allow_user_signups": defaults["allow_user_signups"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        event_pk = resp.json()["id"]
        resp = self.client.post(f"/api/events/{event_pk}/open_signups/")
        self.assertEqual(resp.status_code, 200, resp.content)

        event = Event.objects.nocache().get(pk=event_pk)
        with self.assertRaisesMessage(ValueError, SELF_SERVE_DISABLED_MESSAGE):
            process_rsvp(event, self.player)
