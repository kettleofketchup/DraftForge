from typing import Any
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from app.models import CustomUser
from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.ledger import SignupActor
from events.models import Event, EventSignup, SignupLedgerEntry
from events.serializers import EventSignupSerializer
from events.services import staff_add_signup
from events.tests.base import EventTestCase
from org.models import OrgLog
from tests.test_auth import bulk_rsvp_for_event

STAFF_ENDPOINTS: list[tuple[str, str | None, SignupAction, bool]] = [
    ("admin_signup", None, SignupAction.STAFF_ADDED, True),
    ("approve", SignupStatus.RSVP, SignupAction.APPROVED, True),
    ("reject", SignupStatus.RSVP, SignupAction.REJECTED, True),
    ("confirm", SignupStatus.APPROVED, SignupAction.CONFIRMED, True),
    ("unconfirm", SignupStatus.CONFIRMED, SignupAction.UNCONFIRMED, True),
    ("demote", SignupStatus.APPROVED, SignupAction.DEMOTED, True),
    ("cancel_signup", SignupStatus.APPROVED, SignupAction.WITHDREW, False),
    ("reinstate", SignupStatus.CANCELLED, SignupAction.REINSTATED, True),
]

SIGNUP_URL_NAMES: dict[str, str] = {
    "approve": "event-signup-approve",
    "reject": "event-signup-reject",
    "confirm": "event-signup-confirm",
    "unconfirm": "event-signup-unconfirm",
    "demote": "event-signup-demote",
    "cancel_signup": "event-signup-cancel-signup",
    "reinstate": "event-signup-reinstate",
}


@patch("events.services.notify_signup_changed")
class SignupLedgerWebTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()

    def _entries(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event=event)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )

    def _call(
        self,
        endpoint: str,
        *,
        actor: CustomUser,
        event: Event,
        subject: CustomUser,
        start: str | None,
        data: dict[str, Any] | None = None,
    ) -> tuple[Any, EventSignup | None]:
        self.client.force_authenticate(actor)
        if endpoint == "admin_signup":
            url = f"/api/events/{event.pk}/admin-signup/"
            response = self.client.post(url, {"user_id": subject.pk}, format="json")
            return response, None
        signup = EventSignup.objects.create(event=event, user=subject, status=start)
        url = reverse(SIGNUP_URL_NAMES[endpoint], args=[signup.pk])
        response = self.client.post(url, data or {}, format="json")
        return response, signup

    def _single(self, event: Event) -> SignupLedgerEntry:
        entries = self._entries(event)
        self.assertEqual(len(entries), 1, [e.action for e in entries])
        return entries[0]

    def test_staff_endpoint_roles(self, _notify: Any) -> None:
        for endpoint, start, action, staff_only in STAFF_ENDPOINTS:
            with self.subTest(endpoint=endpoint, row="staff_on_other"):
                event = self.make_event()
                response, _ = self._call(
                    endpoint,
                    actor=self.admin,
                    event=event,
                    subject=self.user,
                    start=start,
                )
                self.assertLess(response.status_code, 300, response.content)
                entry = self._single(event)
                self.assertEqual(entry.action, action)
                self.assertEqual(entry.actor_role, ActorRole.STAFF)
                self.assertEqual(entry.actor_user_id, self.admin.pk)
                self.assertEqual(entry.subject_user_id, self.user.pk)
                self.assertEqual(entry.means, SignupMeans.WEB)
                self.assertTrue(entry.on_behalf)
                self.assertEqual(entry.correlation_id, "")
                self.assertNotIn("staff_power", entry.after["extra"])

            with self.subTest(endpoint=endpoint, row="staff_on_self"):
                event = self.make_event()
                response, _ = self._call(
                    endpoint,
                    actor=self.admin,
                    event=event,
                    subject=self.admin,
                    start=start,
                )
                self.assertLess(response.status_code, 300, response.content)
                entry = self._single(event)
                self.assertEqual(entry.action, action)
                self.assertEqual(entry.actor_role, ActorRole.MEMBER)
                self.assertEqual(entry.actor_user_id, self.admin.pk)
                self.assertEqual(entry.subject_user_id, self.admin.pk)
                self.assertEqual(entry.means, SignupMeans.WEB)
                self.assertFalse(entry.on_behalf)
                if staff_only:
                    self.assertIs(entry.after["extra"]["staff_power"], True)
                else:
                    self.assertNotIn("staff_power", entry.after["extra"])

    def test_owner_cancels_own_records_member(self, _notify: Any) -> None:
        event = self.make_event()
        response, signup = self._call(
            "cancel_signup",
            actor=self.user,
            event=event,
            subject=self.user,
            start=SignupStatus.APPROVED,
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = self._single(event)
        assert signup is not None
        self.assertEqual(entry.action, SignupAction.WITHDREW)
        self.assertEqual(entry.signup_id, signup.pk)
        self.assertEqual(entry.actor_role, ActorRole.MEMBER)
        self.assertEqual(entry.actor_user_id, self.user.pk)
        self.assertEqual(entry.means, SignupMeans.WEB)
        self.assertFalse(entry.on_behalf)
        self.assertNotIn("staff_power", entry.after["extra"])

    def test_staff_reinstates_own_signup_flags_staff_power(self, _notify: Any) -> None:
        rows: list[tuple[str, CustomUser, bool]] = [
            ("staff_own", self.admin, True),
            ("member_own", self.user, False),
        ]
        for name, actor, flagged in rows:
            with self.subTest(row=name):
                event = self.make_event()
                response, _ = self._call(
                    "reinstate",
                    actor=actor,
                    event=event,
                    subject=actor,
                    start=SignupStatus.CANCELLED,
                )
                self.assertEqual(response.status_code, 200, response.content)
                entry = self._single(event)
                self.assertEqual(entry.action, SignupAction.REINSTATED)
                self.assertEqual(entry.actor_role, ActorRole.MEMBER)
                self.assertFalse(entry.on_behalf)
                if flagged:
                    self.assertIs(entry.after["extra"]["staff_power"], True)
                else:
                    self.assertNotIn("staff_power", entry.after["extra"])

        with self.subTest(row="staff_cancels_own"):
            event = self.make_event()
            response, _ = self._call(
                "cancel_signup",
                actor=self.admin,
                event=event,
                subject=self.admin,
                start=SignupStatus.APPROVED,
            )
            self.assertEqual(response.status_code, 200, response.content)
            entry = self._single(event)
            self.assertEqual(entry.actor_role, ActorRole.MEMBER)
            self.assertNotIn("staff_power", entry.after["extra"])

    def test_approve_mmr_override_records_extra_and_org_log(self, _notify: Any) -> None:
        event = self.make_event()
        response, _ = self._call(
            "approve",
            actor=self.admin,
            event=event,
            subject=self.user,
            start=SignupStatus.RSVP,
            data={"mmr": 4200},
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = self._single(event)
        self.assertEqual(entry.after["extra"]["mmr_override"], 4200)
        self.assertIn("game_type", entry.after["extra"])
        log = OrgLog.objects.get(action="set_mmr", target_user=self.user)
        self.assertEqual(log.actor_id, self.admin.pk)
        self.assertEqual(log.details["mmr"], 4200)
        self.assertEqual(log.details["event_id"], event.pk)

    def test_response_shape_unchanged(self, _notify: Any) -> None:
        for endpoint, start, _action, _staff_only in STAFF_ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                event = self.make_event()
                response, _ = self._call(
                    endpoint,
                    actor=self.admin,
                    event=event,
                    subject=self.user,
                    start=start,
                )
                self.assertLess(response.status_code, 300, response.content)
                signup = EventSignup.objects.nocache().get(event=event, user=self.user)
                expected = EventSignupSerializer(
                    signup, context={"request": response.wsgi_request}
                ).data
                self.assertEqual(set(response.data.keys()), set(expected.keys()))

    def _staff_actor(self) -> SignupActor:
        return SignupActor(user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB)

    def test_staff_add_records_reason(self, _notify: Any) -> None:
        event = self.make_event()
        staff_add_signup(event, self.user, actor=self._staff_actor(), reason="x")
        entry = self._single(event)
        self.assertEqual(entry.action, SignupAction.STAFF_ADDED)
        self.assertEqual(entry.reason, "x")

        other = self.make_event()
        staff_add_signup(other, self.user, actor=self._staff_actor())
        default_entry = self._single(other)
        self.assertEqual(default_entry.action, SignupAction.STAFF_ADDED)
        self.assertEqual(default_entry.reason, "")

    def test_staff_readd_cancelled_records_reason(self, _notify: Any) -> None:
        event = self.make_event(max_players=1)
        EventSignup.objects.create(
            event=event, user=self.admin, status=SignupStatus.APPROVED
        )
        EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.CANCELLED
        )
        signup = staff_add_signup(
            event, self.user, actor=self._staff_actor(), reason="y"
        )
        self.assertEqual(signup.status, SignupStatus.WAITLISTED)
        entry = self._single(event)
        self.assertEqual(entry.action, SignupAction.STAFF_ADDED)
        self.assertEqual(entry.reason, "y")
        self.assertIsNotNone(entry.before)


@override_settings(DEBUG=True, TEST=True, RELEASE=False, NODE_ENV="test")
@patch("events.services.notify_signup_changed")
class BulkRsvpLedgerTests(EventTestCase):
    def test_bulk_rsvp_records_system_entries(self, _notify: Any) -> None:
        event = self.make_event()
        users = [self.make_user(), self.make_user()]
        request = APIRequestFactory().post(
            f"/api/tests/events/{event.pk}/bulk-rsvp/",
            {"user_pks": [u.pk for u in users]},
            format="json",
        )
        response = bulk_rsvp_for_event(request, event.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 2)
        entries = list(
            SignupLedgerEntry.objects.filter(event=event)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )
        self.assertEqual(
            [(e.action, e.subject_user_id) for e in entries],
            [(SignupAction.SIGNED_UP, u.pk) for u in users],
        )
        for entry in entries:
            self.assertEqual(entry.actor_role, ActorRole.SYSTEM)
            self.assertEqual(entry.means, SignupMeans.SYSTEM)
            self.assertIsNone(entry.actor_user_id)
            self.assertFalse(entry.on_behalf)
