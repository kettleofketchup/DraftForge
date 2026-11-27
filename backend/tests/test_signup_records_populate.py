from typing import Any
from unittest.mock import patch

from rest_framework.test import APIRequestFactory

from events.constants import SignupAction, SignupStatus
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import teardown_event
from events.tests.base import EventTestCase
from tests.populate.signup_records import (
    populate_signup_records_data,
    signup_records_test_data,
)
from tests.test_signup_records import reset_signup_records, signup_records_data


class SignupRecordsPopulateTest(EventTestCase):
    def setUp(self) -> None:
        for target in (
            "events.services.notify_signup_changed",
            "events.discord.dispatch.notify_signup_changed",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        populate_signup_records_data(force=True)
        self.data: dict[str, Any] = signup_records_test_data()

    def test_idempotent_synthetic_scope_and_real_signup_records(self) -> None:
        first = self.data.copy()
        populate_signup_records_data()
        self.assertEqual(signup_records_test_data(), first)
        org_id = first["org_pk"]
        self.assertEqual(Event.objects.filter(organization_id=org_id).count(), 4)
        self.assertEqual(
            EventSignup.objects.filter(event__organization_id=org_id).count(), 3
        )
        self.assertEqual(
            SignupLedgerEntry.objects.filter(organization_id=org_id).count(), 3
        )
        self.assertEqual(
            set(
                SignupLedgerEntry.objects.filter(organization_id=org_id).values_list(
                    "action", flat=True
                )
            ),
            {SignupAction.SIGNED_UP},
        )
        self.assertEqual(
            set(
                EventSignup.objects.filter(event__organization_id=org_id).values_list(
                    "status", flat=True
                )
            ),
            {SignupStatus.APPROVED},
        )

    def test_force_reset_removes_only_own_live_and_orphan_history(self) -> None:
        unrelated = SignupLedgerEntry.objects.create(
            event=self.event,
            event_snapshot={"id": self.event.pk},
            subject_snapshot={"user_id": self.user.pk},
            organization=self.org,
            subject_user=self.user,
            action=SignupAction.SIGNED_UP,
            actor_role="system",
            means="system",
        )
        own_event_id = self.data["delete_event_pk"]
        own_event = Event.objects.get(pk=own_event_id)
        own_org = own_event.organization
        teardown_event(own_event, actor=own_org.owner, confirm_signup_records=True)
        self.assertTrue(
            SignupLedgerEntry.objects.filter(event_id=own_event_id).exists()
        )
        populate_signup_records_data(force=True)
        reset = signup_records_test_data()
        self.assertEqual(reset["org_pk"], self.data["org_pk"])
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())
        self.assertTrue(SignupLedgerEntry.objects.filter(pk=unrelated.pk).exists())
        self.assertFalse(
            SignupLedgerEntry.objects.filter(event_id=own_event_id).exists()
        )
        self.assertEqual(
            SignupLedgerEntry.objects.filter(organization_id=reset["org_pk"]).count(), 3
        )
        populate_signup_records_data(force=True)
        self.assertEqual(
            Event.objects.filter(organization_id=reset["org_pk"]).count(), 4
        )

    def test_endpoints_are_lazy_and_guarded_outside_test_environment(self) -> None:
        factory = APIRequestFactory()
        with patch("tests.test_signup_records.isTestEnvironment", return_value=False):
            self.assertEqual(signup_records_data(factory.get("/")).status_code, 404)
            self.assertEqual(reset_signup_records(factory.post("/")).status_code, 404)
        with patch("tests.test_signup_records.isTestEnvironment", return_value=True):
            response = reset_signup_records(factory.post("/"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                set(response.data),
                {
                    "org_pk",
                    "admin_pk",
                    "staff_pk",
                    "member_pk",
                    "cancel_event_pk",
                    "delete_event_pk",
                    "registered_event_pk",
                    "empty_event_pk",
                    "repeater_pk",
                },
            )
            self.assertEqual(signup_records_data(factory.get("/")).data, response.data)
