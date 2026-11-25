from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import Commitment, EventState, SignupStatus
from events.exceptions import ImmutableFieldError
from events.models import Event, EventSignup
from events.services import (
    cancel_signup,
    create_tentative_signup,
    decline_signup,
    demote_to_waitlist,
    process_rsvp,
    reinstate_signup,
    reject_signup,
)
from events.tests.actors import SYSTEM
from org.models import Organization


class SignupLineStampingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = Organization.objects.create(name="Line Org")
        cls.users = [
            CustomUser.objects.create_user(username=f"line_user_{i}", password="x")
            for i in range(6)
        ]

    def _event(self, max_players: int | None = 10) -> Event:
        return Event.objects.create(
            organization=self.org,
            name="Line Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            max_players=max_players,
        )

    def _age_first(self, signup: EventSignup) -> datetime:
        past = tz.now() - timedelta(days=3)
        EventSignup._base_manager.filter(pk=signup.pk).update(first_signed_up_at=past)
        return past

    def test_process_rsvp_seated_seqs_and_commitment(self) -> None:
        event = self._event()
        signups = [process_rsvp(event, u, actor=SYSTEM) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        for s in signups:
            self.assertEqual(s.status, SignupStatus.RSVP)
            self.assertEqual(s.commitment, Commitment.MAIN)

    def test_process_rsvp_waitlisted_seqs_and_commitment(self) -> None:
        event = self._event(max_players=1)
        signups = [process_rsvp(event, u, actor=SYSTEM) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        self.assertEqual([s.status for s in signups[1:]], [SignupStatus.WAITLISTED] * 2)
        for s in signups:
            self.assertEqual(s.commitment, Commitment.MAIN)

    def test_create_tentative_seqs_and_commitment(self) -> None:
        event = self._event()
        signups = [
            create_tentative_signup(event, u, actor=SYSTEM) for u in self.users[:3]
        ]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        for s in signups:
            self.assertEqual(s.commitment, Commitment.MAYBE)
            self.assertEqual(s.first_commitment, Commitment.MAYBE)

    def test_decline_seqs_and_commitment(self) -> None:
        event = self._event()
        signups = [decline_signup(event, u, actor=SYSTEM) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        for s in signups:
            self.assertEqual(s.status, SignupStatus.CANCELLED)
            self.assertEqual(s.commitment, Commitment.MAIN)
            s.refresh_from_db()
            self.assertIsNone(s.first_signed_up_at)
            self.assertIsNone(s.first_commitment)
            self.assertIsNone(s.first_rsvp_class)

    def test_mixed_create_sites_share_one_sequence(self) -> None:
        event = self._event()
        a = process_rsvp(event, self.users[0], actor=SYSTEM)
        b = create_tentative_signup(event, self.users[1], actor=SYSTEM)
        c = decline_signup(event, self.users[2], actor=SYSTEM)
        self.assertEqual([a.line_seq, b.line_seq, c.line_seq], [1, 2, 3])

    def _assert_carried(
        self,
        new: EventSignup,
        old_pk: int,
        past: datetime,
        later: EventSignup,
        first_commitment: str,
    ) -> None:
        new.refresh_from_db()
        self.assertEqual(new.pk, old_pk)
        self.assertEqual(new.first_signed_up_at, past)
        self.assertEqual(new.first_commitment, first_commitment)
        self.assertGreater(new.line_seq, later.line_seq)
        self.assertGreater(new.signed_up_at, past)

    def test_tentative_to_rsvp_carries_first_fields(self) -> None:
        event = self._event()
        old = create_tentative_signup(event, self.users[0], actor=SYSTEM)
        later = process_rsvp(event, self.users[1], actor=SYSTEM)
        past = self._age_first(old)
        new = process_rsvp(event, self.users[0], actor=SYSTEM)
        self.assertEqual(new.commitment, Commitment.MAIN)
        self._assert_carried(new, old.pk, past, later, Commitment.MAYBE)

    def test_rsvp_to_tentative_carries_first_fields(self) -> None:
        event = self._event()
        old = process_rsvp(event, self.users[0], actor=SYSTEM)
        later = process_rsvp(event, self.users[1], actor=SYSTEM)
        past = self._age_first(old)
        new = create_tentative_signup(event, self.users[0], actor=SYSTEM)
        self.assertEqual(new.commitment, Commitment.MAYBE)
        self._assert_carried(new, old.pk, past, later, Commitment.MAIN)

    def test_decline_then_rsvp_starts_first_fields_at_rsvp(self) -> None:
        event = self._event()
        decline_signup(event, self.users[0], actor=SYSTEM)
        new = process_rsvp(event, self.users[0], actor=SYSTEM)
        new.refresh_from_db()
        self.assertEqual(new.status, SignupStatus.RSVP)
        self.assertEqual(new.first_signed_up_at, new.signed_up_at)
        self.assertEqual(new.first_commitment, Commitment.MAIN)
        self.assertEqual(new.first_rsvp_class, new.rsvp_class)

    def test_decline_then_tentative_starts_first_fields_as_maybe(self) -> None:
        event = self._event()
        decline_signup(event, self.users[0], actor=SYSTEM)
        new = create_tentative_signup(event, self.users[0], actor=SYSTEM)
        new.refresh_from_db()
        self.assertEqual(new.first_signed_up_at, new.signed_up_at)
        self.assertEqual(new.first_commitment, Commitment.MAYBE)

    def test_rsvp_cancel_rsvp_carries_first_fields(self) -> None:
        event = self._event()
        old = process_rsvp(event, self.users[0], actor=SYSTEM)
        later = process_rsvp(event, self.users[1], actor=SYSTEM)
        past = self._age_first(old)
        cancel_signup(old, actor=SYSTEM)
        new = process_rsvp(event, self.users[0], actor=SYSTEM)
        self._assert_carried(new, old.pk, past, later, Commitment.MAIN)

    def test_reinstating_a_decline_sets_first_fields_once(self) -> None:
        event = self._event()
        declined = decline_signup(event, self.users[0], actor=SYSTEM)
        before = tz.now()
        reinstate_signup(declined, actor=SYSTEM)
        declined.refresh_from_db()
        self.assertEqual(declined.status, SignupStatus.RSVP)
        self.assertGreaterEqual(declined.first_signed_up_at, before)
        self.assertEqual(declined.first_commitment, Commitment.MAIN)
        self.assertEqual(declined.first_rsvp_class, declined.rsvp_class)
        declined.first_commitment = Commitment.MAYBE
        with self.assertRaises(ImmutableFieldError):
            declined.save()

    def test_reinstated_tentative_is_main(self) -> None:
        event = self._event()
        signup = create_tentative_signup(event, self.users[0], actor=SYSTEM)
        cancel_signup(signup, actor=SYSTEM)
        signup.refresh_from_db()
        reinstate_signup(signup, actor=SYSTEM)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.RSVP)
        self.assertEqual(signup.commitment, Commitment.MAIN)
        self.assertEqual(signup.first_commitment, Commitment.MAYBE)

    def test_reinstated_tentative_in_roll_call_is_main(self) -> None:
        event = self._event()
        signup = create_tentative_signup(event, self.users[0], actor=SYSTEM)
        cancel_signup(signup, actor=SYSTEM)
        Event.objects.filter(pk=event.pk).update(state=EventState.ROLL_CALL)
        signup = EventSignup.objects.nocache().get(pk=signup.pk)
        reinstate_signup(signup, actor=SYSTEM)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self.assertEqual(signup.commitment, Commitment.MAIN)

    def test_reject_to_rsvp_carries_first_fields(self) -> None:
        event = self._event()
        old = process_rsvp(event, self.users[0], actor=SYSTEM)
        later = process_rsvp(event, self.users[1], actor=SYSTEM)
        past = self._age_first(old)
        reject_signup(old, actor=SYSTEM)
        new = process_rsvp(event, self.users[0], actor=SYSTEM)
        self._assert_carried(new, old.pk, past, later, Commitment.MAIN)

    def _list_order(self, event: Event) -> list[int]:
        response = APIClient().get(reverse("event-signup-list"), {"event": event.pk})
        self.assertEqual(response.status_code, 200)
        return [
            row["id"]
            for row in response.json()
            if row["status"] == SignupStatus.WAITLISTED
        ]

    def _waitlist_order(self, event: Event) -> list[int]:
        return list(
            EventSignup.objects.filter(event=event, status=SignupStatus.WAITLISTED)
            .order_by("waitlist_position")
            .values_list("pk", flat=True)
        )

    def test_demote_converges_line_with_waitlist_order(self) -> None:
        event = self._event(max_players=3)
        a, _b, _c = (process_rsvp(event, u, actor=SYSTEM) for u in self.users[:3])
        d = process_rsvp(event, self.users[3], actor=SYSTEM)
        self.assertEqual(d.status, SignupStatus.WAITLISTED)
        demote_to_waitlist(a, actor=SYSTEM)
        self.assertEqual(self._list_order(event), [d.pk, a.pk])
        self.assertEqual(self._waitlist_order(event), [d.pk, a.pk])

    def test_reinstate_to_waitlist_diverges_line_from_waitlist_order(self) -> None:
        """Pins current behaviour: reinstate onto the waitlist keeps the old line_seq."""
        event = self._event(max_players=3)
        a = process_rsvp(event, self.users[0], actor=SYSTEM)
        process_rsvp(event, self.users[1], actor=SYSTEM)
        process_rsvp(event, self.users[2], actor=SYSTEM)
        cancel_signup(a, actor=SYSTEM)
        process_rsvp(event, self.users[3], actor=SYSTEM)
        e = process_rsvp(event, self.users[4], actor=SYSTEM)
        self.assertEqual(e.status, SignupStatus.WAITLISTED)
        a.refresh_from_db()
        reinstate_signup(a, actor=SYSTEM)
        a.refresh_from_db()
        self.assertEqual(a.status, SignupStatus.WAITLISTED)
        self.assertEqual(a.line_seq, 1)
        self.assertEqual(self._list_order(event), [a.pk, e.pk])
        self.assertEqual(self._waitlist_order(event), [e.pk, a.pk])
