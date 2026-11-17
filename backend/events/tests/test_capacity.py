from datetime import timedelta

from django.test import TransactionTestCase, override_settings
from django.utils import timezone as tz
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from app.models import CustomUser, Organization
from events.capacity import count_seats, has_free_seat
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.serializers import EventSignupSerializer
from events.services import (
    _promote_from_waitlist,
    cancel_signup,
    create_tentative_signup,
    process_rsvp,
)
from events.tests.base import EventTestCase
from events.views import EventSignupViewSet, _annotate_event_qs


class SeatCapacityTests(EventTestCase):
    def _waitlist(self, event: Event, user: CustomUser, position: int) -> EventSignup:
        return EventSignup.objects.create(
            event=event,
            user=user,
            status=SignupStatus.WAITLISTED,
            waitlist_position=position,
        )

    def test_tentative_does_not_take_a_seat(self) -> None:
        event = self.make_event(max_players=2)
        a, b, c = self.make_user(), self.make_user(), self.make_user()
        create_tentative_signup(event, a)
        process_rsvp(event, b)
        self.assertEqual(process_rsvp(event, c).status, SignupStatus.APPROVED)

    def test_cancel_promotes_past_tentative(self) -> None:
        event = self.make_event(max_players=1)
        a, b, c = self.make_user(), self.make_user(), self.make_user()
        b_signup = process_rsvp(event, b)
        c_signup = process_rsvp(event, c)
        self.assertEqual(c_signup.status, SignupStatus.WAITLISTED)
        create_tentative_signup(event, a)

        cancel_signup(b_signup)

        c_signup.refresh_from_db()
        self.assertEqual(c_signup.status, SignupStatus.APPROVED)
        self.assertIsNone(c_signup.waitlist_position)

    def test_tentative_upgrade_when_full_waitlists(self) -> None:
        event = self.make_event(max_players=1)
        a, b = self.make_user(), self.make_user()
        process_rsvp(event, b)
        create_tentative_signup(event, a)
        self.assertEqual(process_rsvp(event, a).status, SignupStatus.WAITLISTED)

    def test_cancel_tentative_promotes_nobody(self) -> None:
        event = self.make_event(max_players=2)
        a, b, c = self.make_user(), self.make_user(), self.make_user()
        process_rsvp(event, b)
        a_signup = create_tentative_signup(event, a)
        c_signup = self._waitlist(event, c, 1)

        cancel_signup(a_signup)

        c_signup.refresh_from_db()
        self.assertEqual(c_signup.status, SignupStatus.WAITLISTED)

    def test_one_cancel_fills_every_free_seat(self) -> None:
        event = self.make_event(max_players=1)
        b, c, d = self.make_user(), self.make_user(), self.make_user()
        b_signup = process_rsvp(event, b)
        c_signup = self._waitlist(event, c, 1)
        d_signup = self._waitlist(event, d, 2)
        Event.objects.filter(pk=event.pk).update(max_players=3)
        self.assertEqual(b_signup.event.max_players, 1)

        cancel_signup(b_signup)

        c_signup.refresh_from_db()
        d_signup.refresh_from_db()
        self.assertEqual(c_signup.status, SignupStatus.APPROVED)
        self.assertEqual(d_signup.status, SignupStatus.APPROVED)

    def test_lowered_max_players_promotes_nobody(self) -> None:
        event = self.make_event(max_players=3)
        users = [self.make_user() for _ in range(4)]
        signups = [process_rsvp(event, u) for u in users[:3]]
        waitlisted = self._waitlist(event, users[3], 1)
        Event.objects.filter(pk=event.pk).update(max_players=1)
        self.assertEqual(signups[0].event.max_players, 3)

        cancel_signup(signups[0])

        waitlisted.refresh_from_db()
        self.assertEqual(waitlisted.status, SignupStatus.WAITLISTED)
        self.assertFalse(has_free_seat(Event.objects.get(pk=event.pk)))

    def test_count_seats_allow_list(self) -> None:
        event = self.make_event()
        for status in SignupStatus.values:
            EventSignup.objects.create(
                event=event, user=self.make_user(), status=status
            )
        self.assertEqual(count_seats(event), 4)


class SeatCountSurfacesTests(EventTestCase):
    def _one_signup_per_status(self) -> Event:
        event = self.make_event()
        for status in SignupStatus.values:
            EventSignup.objects.create(
                event=event, user=self.make_user(), status=status
            )
        return event

    def test_counts_agree_for_every_status(self) -> None:
        event = self._one_signup_per_status()

        annotated = _annotate_event_qs(Event.objects.filter(pk=event.pk)).get()
        rows = self.client.get("/api/events/signups/", {"event": event.pk}).json()

        self.assertEqual(annotated.signup_count, count_seats(event))
        self.assertEqual(sum(r["holds_seat"] for r in rows), count_seats(event))

    @override_settings(CACHEOPS_ENABLED=False)
    def test_signup_list_holds_seat_no_extra_queries(self) -> None:
        event = self._one_signup_per_status()
        view = EventSignupViewSet()
        view.request = Request(
            APIRequestFactory().get("/api/events/signups/", {"event": event.pk})
        )
        signups = list(view.get_queryset())
        serializer = EventSignupSerializer()

        with self.assertNumQueries(0):
            flags = [serializer.get_holds_seat(s) for s in signups]

        self.assertEqual(sum(flags), count_seats(event))


class PromoteRequiresAtomicTests(TransactionTestCase):
    def setUp(self) -> None:
        owner = CustomUser.objects.create_user(username="atomic_owner", password="x")
        org = Organization.objects.create(name="Atomic Org", owner=owner)
        self.event = Event.objects.create(
            organization=org,
            name="Atomic Event",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            created_by=owner,
            max_players=2,
        )

    def test_promote_requires_atomic(self) -> None:
        with self.assertRaises(AssertionError):
            _promote_from_waitlist(self.event)
