from datetime import timedelta

from django.utils import timezone as tz
from rest_framework import status
from rest_framework.test import APIClient

from events.models import Event, EventSignup, EventState, SignupStatus
from events.tests.base import EventTestCase


class EventAPITests(EventTestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_event(self, **kwargs):
        defaults = dict(
            organization=self.org,
            name="API Event",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.UPCOMING,
            created_by=self.admin,
            tournament_name="API Tourney",
            tournament_league=self.league,
        )
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def test_list_events_public(self):
        self._create_event()
        r = self.client.get("/api/events/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_create_event_requires_auth(self):
        r = self.client.post("/api/events/", {})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_rsvp_for_event(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/{event.pk}/rsvp/")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], SignupStatus.RSVP)

    def test_rsvp_duplicate_rejected(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        self.client.force_authenticate(user=self.user)
        self.client.post(f"/api/events/{event.pk}/rsvp/")
        r = self.client.post(f"/api/events/{event.pk}/rsvp/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_open_signups_requires_staff(self):
        event = self._create_event()
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/{event.pk}/open_signups/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_open_signups_as_staff(self):
        event = self._create_event()
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/events/{event.pk}/open_signups/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.SIGNUPS_OPEN)

    def test_cancel_event(self):
        event = self._create_event()
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/events/{event.pk}/cancel/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_approve_signup_requires_staff(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/signups/{signup.pk}/approve/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_signup_as_staff(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/events/signups/{signup.pk}/approve/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)

    def test_cancel_own_signup(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/signups/{signup.pk}/cancel_signup/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_cannot_cancel_others_signup(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.admin, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/signups/{signup.pk}/cancel_signup/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_organization(self):
        self._create_event()
        r = self.client.get(f"/api/events/?organization={self.org.pk}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)

    def test_filter_by_state(self):
        self._create_event(state=EventState.SIGNUPS_OPEN)
        self._create_event(
            name="F",
            state=EventState.UPCOMING,
            scheduled_at=tz.now() + timedelta(days=14),
        )
        r = self.client.get("/api/events/?state=signups_open")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)
