from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from events.constants import Commitment, EventState, SignupStatus
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
        signups = [process_rsvp(event, u) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        for s in signups:
            self.assertEqual(s.status, SignupStatus.RSVP)
            self.assertEqual(s.commitment, Commitment.MAIN)

    def test_process_rsvp_waitlisted_seqs_and_commitment(self) -> None:
        event = self._event(max_players=1)
        signups = [process_rsvp(event, u) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        self.assertEqual([s.status for s in signups[1:]], [SignupStatus.WAITLISTED] * 2)
        for s in signups:
            self.assertEqual(s.commitment, Commitment.MAIN)

    def test_create_tentative_seqs_and_commitment(self) -> None:
        event = self._event()
        signups = [create_tentative_signup(event, u) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        for s in signups:
            self.assertEqual(s.commitment, Commitment.MAYBE)
            self.assertEqual(s.first_commitment, Commitment.MAYBE)

    def test_decline_seqs_and_commitment(self) -> None:
        event = self._event()
        signups = [decline_signup(event, u) for u in self.users[:3]]
        self.assertEqual([s.line_seq for s in signups], [1, 2, 3])
        for s in signups:
            self.assertEqual(s.status, SignupStatus.CANCELLED)
            self.assertEqual(s.commitment, Commitment.MAIN)

    def test_mixed_create_sites_share_one_sequence(self) -> None:
        event = self._event()
        a = process_rsvp(event, self.users[0])
        b = create_tentative_signup(event, self.users[1])
        c = decline_signup(event, self.users[2])
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
        self.assertNotEqual(new.pk, old_pk)
        self.assertFalse(EventSignup.objects.filter(pk=old_pk).exists())
        self.assertEqual(new.first_signed_up_at, past)
        self.assertEqual(new.first_commitment, first_commitment)
        self.assertGreater(new.line_seq, later.line_seq)
        self.assertGreater(new.signed_up_at, past)

    def test_tentative_to_rsvp_carries_first_fields(self) -> None:
        event = self._event()
        old = create_tentative_signup(event, self.users[0])
        later = process_rsvp(event, self.users[1])
        past = self._age_first(old)
        new = process_rsvp(event, self.users[0])
        self.assertEqual(new.commitment, Commitment.MAIN)
        self._assert_carried(new, old.pk, past, later, Commitment.MAYBE)

    def test_rsvp_to_tentative_carries_first_fields(self) -> None:
        event = self._event()
        old = process_rsvp(event, self.users[0])
        later = process_rsvp(event, self.users[1])
        past = self._age_first(old)
        new = create_tentative_signup(event, self.users[0])
        self.assertEqual(new.commitment, Commitment.MAYBE)
        self._assert_carried(new, old.pk, past, later, Commitment.MAIN)

    def test_decline_to_rsvp_carries_first_fields(self) -> None:
        event = self._event()
        old = decline_signup(event, self.users[0])
        later = process_rsvp(event, self.users[1])
        past = self._age_first(old)
        new = process_rsvp(event, self.users[0])
        self.assertEqual(new.status, SignupStatus.RSVP)
        self._assert_carried(new, old.pk, past, later, Commitment.MAIN)

    def test_reject_to_rsvp_carries_first_fields(self) -> None:
        event = self._event()
        old = process_rsvp(event, self.users[0])
        later = process_rsvp(event, self.users[1])
        past = self._age_first(old)
        reject_signup(old)
        new = process_rsvp(event, self.users[0])
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

    def test_demote_diverges_line_from_waitlist_order(self) -> None:
        """Pinned for #493: demote sets waitlist_position only, not line_seq."""
        event = self._event(max_players=3)
        a, _b, _c = (process_rsvp(event, u) for u in self.users[:3])
        d = process_rsvp(event, self.users[3])
        self.assertEqual(d.status, SignupStatus.WAITLISTED)
        demote_to_waitlist(a)
        self.assertEqual(self._list_order(event), [a.pk, d.pk])
        self.assertEqual(self._waitlist_order(event), [d.pk, a.pk])

    def test_reinstate_to_waitlist_diverges_line_from_waitlist_order(self) -> None:
        """Pinned for #493: reinstate onto the waitlist keeps the old line_seq."""
        event = self._event(max_players=3)
        a = process_rsvp(event, self.users[0])
        process_rsvp(event, self.users[1])
        process_rsvp(event, self.users[2])
        cancel_signup(a)
        process_rsvp(event, self.users[3])
        e = process_rsvp(event, self.users[4])
        self.assertEqual(e.status, SignupStatus.WAITLISTED)
        a.refresh_from_db()
        reinstate_signup(a)
        a.refresh_from_db()
        self.assertEqual(a.status, SignupStatus.WAITLISTED)
        self.assertEqual(a.line_seq, 1)
        self.assertEqual(self._list_order(event), [a.pk, e.pk])
        self.assertEqual(self._waitlist_order(event), [e.pk, a.pk])
