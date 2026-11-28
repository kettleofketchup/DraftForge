from typing import Any
from unittest.mock import patch

from rest_framework.test import APIRequestFactory

from events.ledger import LEDGER_STATE_DELETED, RecordsWindow
from events.models import Event, SignupLedgerEntry
from events.records import RecordsFilter, build_signup_records
from events.tests.base import EventTestCase
from org.models import OrgSettings
from org.settings_service import get_org_settings
from tests.populate.signup_records_export import (
    populate_signup_records_export_data,
    signup_records_export_test_data,
)
from tests.test_signup_records_export import (
    reset_signup_records_export,
    signup_records_export_data,
)

DATA_KEYS: set[str] = {
    "org_pk",
    "staff_pk",
    "admin_pk",
    "member_pk",
    "kept_event_pk",
    "cancelled_event_pk",
    "deleted_event_pk",
    "deleted_event_name",
}


class SignupRecordsExportPopulateTest(EventTestCase):
    def setUp(self) -> None:
        for target in (
            "events.services.notify_signup_changed",
            "events.discord.dispatch.notify_signup_changed",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        populate_signup_records_export_data(force=True)
        self.data: dict[str, Any] = signup_records_export_test_data()

    def test_idempotent(self) -> None:
        org_id = self.data["org_pk"]
        rows = SignupLedgerEntry.objects.filter(organization_id=org_id).count()
        populate_signup_records_export_data()
        self.assertEqual(signup_records_export_test_data(), self.data)
        self.assertEqual(
            SignupLedgerEntry.objects.filter(organization_id=org_id).count(), rows
        )
        self.assertEqual(Event.objects.filter(organization_id=org_id).count(), 2)

    def test_deleted_event_keeps_ledger_rows(self) -> None:
        deleted = self.data["deleted_event_pk"]
        self.assertFalse(Event.objects.filter(pk=deleted).exists())
        self.assertTrue(SignupLedgerEntry.objects.filter(event_id=deleted).exists())

    def test_records_include_deleted_and_cancelled_rows(self) -> None:
        records = build_signup_records(
            self.data["org_pk"], RecordsFilter(RecordsWindow())
        )
        states = {(r.event_id, r.event_state) for r in records}
        self.assertIn((self.data["deleted_event_pk"], LEDGER_STATE_DELETED), states)
        self.assertIn((self.data["cancelled_event_pk"], "cancelled"), states)
        self.assertEqual(len(records), 9)
        deleted_names = {
            r.event_name for r in records if r.event_id == self.data["deleted_event_pk"]
        }
        self.assertEqual(deleted_names, {self.data["deleted_event_name"]})

    def test_force_reset_rebuilds_and_clears_retention(self) -> None:
        org_id = self.data["org_pk"]
        settings_row = get_org_settings(org_id)
        OrgSettings.objects.filter(pk=settings_row.pk).update(
            signup_record_retention_days=365
        )
        populate_signup_records_export_data(force=True)
        reset = signup_records_export_test_data()
        self.assertNotEqual(reset["kept_event_pk"], self.data["kept_event_pk"])
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event_id=self.data["deleted_event_pk"]
            ).exists()
        )
        self.assertIsNone(
            OrgSettings.objects.nocache()
            .filter(organization_id=org_id)
            .values_list("signup_record_retention_days", flat=True)
            .first()
        )

    def test_endpoints_are_lazy_and_guarded_outside_test_environment(self) -> None:
        factory = APIRequestFactory()
        target = "tests.test_signup_records_export.isTestEnvironment"
        with patch(target, return_value=False):
            self.assertEqual(
                signup_records_export_data(factory.get("/")).status_code, 404
            )
            self.assertEqual(
                reset_signup_records_export(factory.post("/")).status_code, 404
            )
        with patch(target, return_value=True):
            response = reset_signup_records_export(factory.post("/"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.data), DATA_KEYS)
            self.assertEqual(
                signup_records_export_data(factory.get("/")).data, response.data
            )
