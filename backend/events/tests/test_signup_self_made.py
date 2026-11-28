from rest_framework.test import APIClient

from events.discord._shared import _direct_signup
from events.models import Event, EventSignup, SignupStatus
from events.services import (
    cancel_signup,
    create_tentative_signup,
    process_rsvp,
    staff_add_signup,
)
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase


class SignupSelfMadeTests(EventTestCase):
    def setUp(self) -> None:
        self.open_event: Event = self.make_event()
        self.member = self.make_user()

    def _row(self) -> EventSignup:
        return EventSignup.objects.get(event=self.open_event, user=self.member)

    def test_process_rsvp_marks_self_made(self) -> None:
        signup = process_rsvp(self.open_event, self.member, actor=SYSTEM)
        self.assertTrue(signup.self_made)
        self.assertTrue(self._row().self_made)

    def test_tentative_marks_self_made(self) -> None:
        signup = create_tentative_signup(self.open_event, self.member, actor=SYSTEM)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertTrue(self._row().self_made)

    def test_staff_add_signup_not_self_made(self) -> None:
        signup = staff_add_signup(self.open_event, self.member, actor=SYSTEM)
        self.assertFalse(signup.self_made)
        self.assertFalse(self._row().self_made)

    def test_resignup_after_cancel_self_made(self) -> None:
        staff_row = staff_add_signup(self.open_event, self.member, actor=SYSTEM)
        self.assertFalse(staff_row.self_made)
        cancel_signup(staff_row, actor=SYSTEM)
        signup = process_rsvp(self.open_event, self.member, actor=SYSTEM)
        self.assertEqual(signup.pk, staff_row.pk)
        self.assertTrue(self._row().self_made)

    def test_waitlisted_signup_self_made(self) -> None:
        full_event = self.make_event(max_players=1)
        process_rsvp(full_event, self.make_user(), actor=SYSTEM)
        signup = process_rsvp(full_event, self.member, actor=SYSTEM)
        self.assertEqual(signup.status, SignupStatus.WAITLISTED)
        self.assertTrue(
            EventSignup.objects.get(event=full_event, user=self.member).self_made
        )

    def test_web_signup_view_self_made(self) -> None:
        client = APIClient()
        client.force_authenticate(self.member)
        resp = client.post(
            f"/api/events/{self.open_event.pk}/signup/",
            {"intent": "rsvp", "profile": {}},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(self._row().self_made)

    def test_discord_direct_signup_self_made(self) -> None:
        result = _direct_signup(self.open_event, self.member)
        self.assertEqual(result["action"], "signed_up")
        self.assertTrue(self._row().self_made)
