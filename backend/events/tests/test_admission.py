from datetime import time, timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from events.admission import NOT_ACCEPTING_MESSAGE, SELF_SERVE_DISABLED_MESSAGE
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
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase
from tests.cache import flush_run_cache
from tournament.models import Tournament

LIST_URL = "/api/tournaments-list/?open_signups=1"


class SelfServeAdmissionTests(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.closed = self.make_event(allow_user_signups=False)
        self.player = self.make_user()

    def test_process_rsvp_refused_when_self_serve_off(self) -> None:
        with self.assertRaisesMessage(ValueError, SELF_SERVE_DISABLED_MESSAGE):
            process_rsvp(self.closed, self.player, actor=SYSTEM)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_tentative_refused(self) -> None:
        with self.assertRaisesMessage(ValueError, SELF_SERVE_DISABLED_MESSAGE):
            create_tentative_signup(self.closed, self.player, actor=SYSTEM)
        self.assertFalse(EventSignup.objects.filter(event=self.closed).exists())

    def test_wrong_state_keeps_existing_message(self) -> None:
        upcoming = self.make_event(state=EventState.UPCOMING)
        with self.assertRaisesMessage(ValueError, "Event is not accepting signups."):
            process_rsvp(upcoming, self.player, actor=SYSTEM)

    def test_decline_allowed(self) -> None:
        signup = decline_signup(self.closed, self.player, actor=SYSTEM)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

    def _reinstate(self, signup: EventSignup, user: object) -> object:
        self.client.force_authenticate(user=user)
        return self.client.post(f"/api/events/signups/{signup.pk}/reinstate/")

    def test_owner_reinstate_refused_when_self_serve_off(self) -> None:
        signup = decline_signup(self.closed, self.player, actor=SYSTEM)

        resp = self._reinstate(signup, self.player)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["error"], SELF_SERVE_DISABLED_MESSAGE)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

        resp = self._reinstate(signup, self.admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        signup.refresh_from_db()
        self.assertNotEqual(signup.status, SignupStatus.CANCELLED)

    def test_owner_reinstate_refused_during_roll_call(self) -> None:
        event = self.make_event(state=EventState.ROLL_CALL)
        signup = EventSignup.objects.create(
            event=event, user=self.player, status=SignupStatus.REJECTED
        )
        resp = self._reinstate(signup, self.player)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["error"], NOT_ACCEPTING_MESSAGE)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.REJECTED)

        resp = self._reinstate(signup, self.admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)

    def test_owner_reinstate_allowed_when_self_serve_on(self) -> None:
        event = self.make_event()
        signup = decline_signup(event, self.player, actor=SYSTEM)
        resp = self._reinstate(signup, self.player)
        self.assertEqual(resp.status_code, 200, resp.content)
        signup.refresh_from_db()
        self.assertNotEqual(signup.status, SignupStatus.CANCELLED)

    def test_staff_add_allowed(self) -> None:
        signup = staff_add_signup(self.closed, self.player, actor=SYSTEM)
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
            process_rsvp(event, self.player, actor=SYSTEM)

    def test_api_created_event_with_flag_off_refuses_self_serve(self) -> None:
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
            process_rsvp(event, self.player, actor=SYSTEM)
