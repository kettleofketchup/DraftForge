import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from cacheops import invalidate_obj
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from org import settings_constants, settings_service
from org.models import Organization, OrgLog, OrgSettings, OrgUser
from org.settings_constants import ALL_CODES, StaffOverridePolicy
from org.settings_service import (
    get_org_settings,
    normalize_warning_codes,
    update_org_settings,
    validate_retention_days,
)

PINNED_MSG = (
    "ALL_CODES changed: adding a code needs a data migration that appends it "
    "to existing rows; removing or renaming one needs a migration that removes "
    "or renames it. Both must hardcode the literal code strings. "
    "See docs/features/organization-settings.md."
)


class OrgSettingsConstantsTest(SimpleTestCase):
    def test_all_codes_pinned(self) -> None:
        self.assertEqual(
            settings_constants.ALL_CODES,
            [
                "gate_outside",
                "gate_out_of_range",
                "over_capacity",
                "special_seat_role_mismatch",
                "maybe_special_seat",
                "maybe_forced_main",
            ],
            PINNED_MSG,
        )

    def test_labels_keyed_by_all_codes(self) -> None:
        self.assertEqual(
            set(settings_constants.WARNING_CODE_LABELS),
            set(settings_constants.ALL_CODES),
        )

    def test_default_warning_codes_fresh_list(self) -> None:
        first = settings_constants.default_warning_codes()
        second = settings_constants.default_warning_codes()
        self.assertEqual(first, settings_constants.ALL_CODES)
        self.assertIsNot(first, settings_constants.ALL_CODES)
        self.assertIsNot(first, second)

    def test_policy_values(self) -> None:
        self.assertEqual(
            [choice.value for choice in StaffOverridePolicy],
            ["silent", "confirm", "block"],
        )


class OrgSettingsModelTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Settings Org")
        self.other_org = Organization.objects.create(name="Other Settings Org")

    def test_defaults(self) -> None:
        row = OrgSettings.objects.create(organization=self.org)
        row.refresh_from_db()
        self.assertEqual(row.staff_override_policy, "silent")
        self.assertEqual(row.staff_override_warning_codes, settings_constants.ALL_CODES)
        self.assertEqual(str(row), f"Settings for {self.org.pk}")

    def test_default_codes_not_shared(self) -> None:
        row_a = OrgSettings.objects.create(organization=self.org)
        row_b = OrgSettings.objects.create(organization=self.other_org)
        row_a.staff_override_warning_codes.append("x")
        self.assertEqual(
            row_b.staff_override_warning_codes, settings_constants.ALL_CODES
        )
        self.assertNotIn("x", settings_constants.ALL_CODES)

    def test_retention_defaults_null(self) -> None:
        row = OrgSettings.objects.create(organization=self.org)
        row.refresh_from_db()
        self.assertIsNone(row.signup_record_retention_days)

    def test_policy_alias(self) -> None:
        self.assertIs(OrgSettings.StaffOverridePolicy, StaffOverridePolicy)

    def test_one_row_per_org(self) -> None:
        OrgSettings.objects.create(organization=self.org)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrgSettings.objects.create(organization=self.org)

    def test_cacheops_registered(self) -> None:
        self.assertEqual(
            settings.CACHEOPS.get("org.orgsettings"),
            {"ops": "all", "timeout": 3600},
        )


class OrgSettingsServiceTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Service Org")
        self.other_org = Organization.objects.create(name="Other Service Org")
        self.actor = CustomUser.objects.create_user(
            username="settings_admin", password="x"
        )

    def _count(self) -> int:
        return OrgSettings.objects.nocache().filter(organization=self.org).count()

    def test_get_creates_row_with_defaults(self) -> None:
        row = get_org_settings(self.org)
        self.assertEqual(row.staff_override_policy, "silent")
        self.assertEqual(row.staff_override_warning_codes, ALL_CODES)
        self.assertEqual(self._count(), 1)

    def test_get_is_idempotent(self) -> None:
        first = get_org_settings(self.org)
        second = get_org_settings(self.org)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self._count(), 1)

    def test_get_accepts_int(self) -> None:
        self.assertEqual(get_org_settings(self.org.pk).organization_id, self.org.pk)

    def test_created_logged_once(self) -> None:
        with (
            mock.patch.object(settings_service, "log") as log,
            self.captureOnCommitCallbacks(execute=True),
        ):
            get_org_settings(self.org)
            get_org_settings(self.org)
        created_calls = [
            c for c in log.info.call_args_list if c.args == ("org_settings_created",)
        ]
        self.assertEqual(len(created_calls), 1)
        self.assertEqual(
            created_calls[0].kwargs,
            {"system": "org", "subsystem": "settings", "org_id": self.org.pk},
        )

    def test_miss_path_returns_existing_row(self) -> None:
        existing = OrgSettings.objects.create(organization=self.org)
        with mock.patch.object(settings_service, "_cached_row", return_value=None):
            row = get_org_settings(self.org)
        self.assertEqual(row.pk, existing.pk)
        self.assertEqual(self._count(), 1)

    def test_get_or_create_integrity_race(self) -> None:
        existing = OrgSettings.objects.create(organization=self.org)
        original_get: Callable[..., Any] = QuerySet.get
        calls = {"n": 0}

        def racing_get(qs: QuerySet, *args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OrgSettings.DoesNotExist
            return original_get(qs, *args, **kwargs)

        with (
            mock.patch.object(settings_service, "_cached_row", return_value=None),
            mock.patch.object(
                QuerySet, "get", autospec=True, side_effect=racing_get
            ) as patched,
        ):
            row = get_org_settings(self.org)
        self.assertGreaterEqual(patched.call_count, 2)
        self.assertEqual(row.pk, existing.pk)
        self.assertEqual(self._count(), 1)

    def test_normalize_warning_codes(self) -> None:
        self.assertEqual(
            normalize_warning_codes(["over_capacity", "gate_outside", "over_capacity"]),
            ["gate_outside", "over_capacity"],
        )
        self.assertEqual(normalize_warning_codes([]), [])
        with self.assertRaisesMessage(ValueError, "Unknown warning code(s): bogus"):
            normalize_warning_codes(["gate_outside", "bogus"])
        for bad in (None, {}, "gate_outside", [1]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_warning_codes(bad)

    def test_normalize_reads_all_codes_at_call_time(self) -> None:
        with mock.patch.object(
            settings_constants, "ALL_CODES", [*ALL_CODES, "new_code"]
        ):
            self.assertEqual(normalize_warning_codes(["new_code"]), ["new_code"])

    def test_update_persists_and_audits(self) -> None:
        get_org_settings(self.org)
        with (
            mock.patch.object(settings_service, "log") as log,
            self.captureOnCommitCallbacks(execute=True),
        ):
            row = update_org_settings(
                self.org,
                actor=self.actor,
                changes={
                    "staff_override_policy": "confirm",
                    "staff_override_warning_codes": ["over_capacity"],
                },
            )
        stored = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertEqual(stored.staff_override_policy, "confirm")
        self.assertEqual(stored.staff_override_warning_codes, ["over_capacity"])
        changed = ["staff_override_policy", "staff_override_warning_codes"]
        logs = OrgLog.objects.filter(organization=self.org)
        self.assertEqual(logs.count(), 1)
        entry = logs.get()
        self.assertEqual(entry.action, "update")
        self.assertEqual(entry.actor, self.actor)
        self.assertEqual(entry.details, {"area": "settings", "changed_fields": changed})
        log.info.assert_any_call(
            "org_settings_updated",
            system="org",
            subsystem="settings",
            org_id=self.org.pk,
            actor_id=self.actor.pk,
            changed_fields=changed,
            staff_override_policy="confirm",
            warning_code_count=1,
            signup_record_retention_days=None,
        )

    def test_update_retention_persists_and_audits(self) -> None:
        get_org_settings(self.org)
        with (
            mock.patch.object(settings_service, "log") as log,
            self.captureOnCommitCallbacks(execute=True),
        ):
            row = update_org_settings(
                self.org,
                actor=self.actor,
                changes={"signup_record_retention_days": 365},
            )
        stored = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertEqual(stored.signup_record_retention_days, 365)
        entry = OrgLog.objects.get(organization=self.org)
        self.assertEqual(
            entry.details,
            {"area": "settings", "changed_fields": ["signup_record_retention_days"]},
        )
        updated = [
            c for c in log.info.call_args_list if c.args[0] == "org_settings_updated"
        ]
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].kwargs["signup_record_retention_days"], 365)

    def test_update_retention_bounds(self) -> None:
        row = get_org_settings(self.org)
        for bad in (29, 36501):
            with self.subTest(days=bad), self.assertRaises(ValueError):
                update_org_settings(
                    self.org,
                    actor=self.actor,
                    changes={"signup_record_retention_days": bad},
                )
        self.assertIsNone(
            OrgSettings.objects.nocache().get(pk=row.pk).signup_record_retention_days
        )
        for good in (30, 36500, None):
            with self.subTest(days=good):
                update_org_settings(
                    self.org,
                    actor=self.actor,
                    changes={"signup_record_retention_days": good},
                )
                self.assertEqual(
                    OrgSettings.objects.nocache()
                    .get(pk=row.pk)
                    .signup_record_retention_days,
                    good,
                )

    def test_validate_retention_days(self) -> None:
        self.assertIsNone(validate_retention_days(None))
        self.assertEqual(validate_retention_days(30), 30)
        self.assertEqual(validate_retention_days(36500), 36500)
        with self.assertRaisesMessage(
            ValueError, "Retention must be at least 30 days."
        ):
            validate_retention_days(29)
        with self.assertRaisesMessage(
            ValueError, "Retention must be at most 36500 days."
        ):
            validate_retention_days(36501)
        for bad in ("x", "60", True, False, 45.0):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validate_retention_days(bad)
        with override_settings(SIGNUP_RECORD_MIN_RETENTION_DAYS=60):
            with self.assertRaisesMessage(
                ValueError, "Retention must be at least 60 days."
            ):
                validate_retention_days(59)
            self.assertEqual(validate_retention_days(60), 60)

    def test_update_noop(self) -> None:
        row = get_org_settings(self.org)
        before = OrgSettings.objects.nocache().get(pk=row.pk).updated_at
        with (
            mock.patch.object(settings_service, "log") as log,
            self.captureOnCommitCallbacks(execute=True),
        ):
            update_org_settings(
                self.org,
                actor=self.actor,
                changes={
                    "staff_override_policy": "silent",
                    "staff_override_warning_codes": list(reversed(ALL_CODES)),
                },
            )
        self.assertEqual(
            OrgSettings.objects.nocache().get(pk=row.pk).updated_at, before
        )
        self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())
        self.assertNotIn(
            "org_settings_updated", [c.args[0] for c in log.info.call_args_list]
        )

    def test_update_rejects_unknown_policy(self) -> None:
        row = get_org_settings(self.org)
        for bad in ("loud", "", None, 1):
            with self.subTest(policy=bad), self.assertRaises(ValueError):
                update_org_settings(
                    self.org,
                    actor=self.actor,
                    changes={
                        "staff_override_policy": bad,
                        "staff_override_warning_codes": ["over_capacity"],
                    },
                )
        after = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertEqual(after.staff_override_policy, "silent")
        self.assertEqual(after.staff_override_warning_codes, list(ALL_CODES))
        self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())

    def test_update_ignores_non_editable_keys(self) -> None:
        row = get_org_settings(self.org)
        before = OrgSettings.objects.nocache().get(pk=row.pk)
        update_org_settings(
            self.org,
            actor=self.actor,
            changes={"organization": self.other_org.pk, "created_at": None},
        )
        after = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertEqual(after.organization_id, self.org.pk)
        self.assertEqual(after.created_at, before.created_at)
        self.assertEqual(after.updated_at, before.updated_at)
        self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())

    def test_update_invalidates_cache(self) -> None:
        get_org_settings(self.org)
        with (
            mock.patch("app.cache_utils._cacheops_invalidate_obj") as invalidate,
            self.captureOnCommitCallbacks(execute=True),
        ):
            row = update_org_settings(
                self.org, actor=self.actor, changes={"staff_override_policy": "block"}
            )
        invalidate.assert_called_once_with(row)
        self.assertEqual(get_org_settings(self.org).staff_override_policy, "block")


def settings_url(org_id: int) -> str:
    return f"/api/organizations/{org_id}/settings/"


class OrgSettingsApiTest(TestCase):
    def setUp(self) -> None:
        self.site_admin = CustomUser.objects.create_user(
            username="orgset_site_admin", password="x", is_staff=True
        )
        self.owner = CustomUser.objects.create_user(
            username="orgset_owner", password="x"
        )
        self.admin = CustomUser.objects.create_user(
            username="orgset_admin", password="x"
        )
        self.staff = CustomUser.objects.create_user(
            username="orgset_staff", password="x"
        )
        self.promoter = CustomUser.objects.create_user(
            username="orgset_promoter", password="x"
        )
        self.member = CustomUser.objects.create_user(
            username="orgset_member", password="x"
        )
        self.org = Organization.objects.create(name="Orgset Org", owner=self.owner)
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        self.org.promoters.add(self.promoter)
        for user in (self.promoter, self.member):
            OrgUser.objects.create(user=user, organization=self.org)

        self.other_owner = CustomUser.objects.create_user(
            username="orgset_other_owner", password="x"
        )
        self.other_admin = CustomUser.objects.create_user(
            username="orgset_other_admin", password="x"
        )
        self.other_org = Organization.objects.create(
            name="Orgset Other Org", owner=self.other_owner
        )
        self.other_org.admins.add(self.other_admin)

        self.client = APIClient()
        self.url = settings_url(self.org.pk)

    def _as(self, user: CustomUser | None) -> APIClient:
        self.client.force_authenticate(user=user)
        return self.client

    def _count(self) -> int:
        return OrgSettings.objects.nocache().count()

    def _row(self, org: Organization) -> OrgSettings:
        return OrgSettings.objects.nocache().get(organization=org)

    def _patch(
        self, user: CustomUser | None, body: Any, org_id: int | None = None
    ) -> Response:
        return self._as(user).patch(
            settings_url(org_id or self.org.pk), body, format="json"
        )

    def test_get_allowed_roles(self) -> None:
        for user in (self.owner, self.admin, self.site_admin):
            with self.subTest(user=user.username):
                response = self._as(user).get(self.url)
                self.assertEqual(response.status_code, 200, response.data)
                data = response.data
                self.assertEqual(
                    set(data),
                    {
                        "organization",
                        "staff_override_policy",
                        "staff_override_warning_codes",
                        "available_warning_codes",
                        "signup_record_retention_days",
                        "signup_record_min_retention_days",
                        "updated_at",
                    },
                )
                self.assertEqual(data["organization"], self.org.pk)
                self.assertIsNone(data["signup_record_retention_days"])
                self.assertEqual(data["staff_override_policy"], "silent")
                self.assertEqual(data["staff_override_warning_codes"], ALL_CODES)
                self.assertEqual(len(data["available_warning_codes"]), 6)
                self.assertEqual(
                    data["available_warning_codes"][0],
                    {"code": "gate_outside", "label": "Outside the signup gate window"},
                )

    def test_get_denied_roles(self) -> None:
        for user in (self.staff, self.promoter, self.member):
            with self.subTest(user=user.username):
                response = self._as(user).get(self.url)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["code"], "not_permitted")
        response = self._as(None).get(self.url)
        self.assertIn(response.status_code, (401, 403))

    def test_get_unknown_org_404(self) -> None:
        response = self._as(self.admin).get(settings_url(999999))
        self.assertEqual(response.status_code, 404)

    def test_get_creates_row(self) -> None:
        self.assertEqual(self._count(), 0)
        response = self._as(self.admin).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._count(), 1)
        self.assertEqual(self._row(self.org).organization_id, self.org.pk)

    def test_denied_requests_create_no_row(self) -> None:
        before = self._count()
        self._as(self.staff).get(self.url)
        self._as(self.member).patch(
            self.url, {"staff_override_policy": "block"}, format="json"
        )
        self._as(None).get(self.url)
        self._as(None).patch(
            self.url, {"staff_override_policy": "block"}, format="json"
        )
        self._as(self.admin).get(settings_url(999999))
        self._as(self.admin).patch(
            settings_url(999999), {"staff_override_policy": "block"}, format="json"
        )
        self.assertEqual(self._count(), before)

    def test_cross_tenant_denied(self) -> None:
        other_url = settings_url(self.other_org.pk)
        for user in (self.owner, self.admin):
            with self.subTest(user=user.username, method="GET"):
                self.assertEqual(self._as(user).get(other_url).status_code, 403)
            with self.subTest(user=user.username, method="PATCH"):
                response = self._patch(
                    user, {"staff_override_policy": "block"}, self.other_org.pk
                )
                self.assertEqual(response.status_code, 403)
        self.assertFalse(
            OrgSettings.objects.nocache().filter(organization=self.other_org).exists()
        )

        get_org_settings(self.other_org)
        before = self._row(self.other_org)
        for user in (self.owner, self.admin):
            response = self._patch(
                user,
                {
                    "staff_override_policy": "block",
                    "staff_override_warning_codes": [],
                },
                self.other_org.pk,
            )
            self.assertEqual(response.status_code, 403)
        after = self._row(self.other_org)
        self.assertEqual(after.staff_override_policy, before.staff_override_policy)
        self.assertEqual(
            after.staff_override_warning_codes, before.staff_override_warning_codes
        )
        self.assertEqual(after.updated_at, before.updated_at)

    def test_patch_allowed_roles(self) -> None:
        body = {
            "staff_override_policy": "confirm",
            "staff_override_warning_codes": ["over_capacity"],
        }
        for user in (self.owner, self.admin, self.site_admin):
            with self.subTest(user=user.username):
                OrgSettings.objects.nocache().filter(organization=self.org).delete()
                response = self._patch(user, body)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["staff_override_policy"], "confirm")
                self.assertEqual(
                    response.data["staff_override_warning_codes"], ["over_capacity"]
                )
                row = self._row(self.org)
                self.assertEqual(row.staff_override_policy, "confirm")
                self.assertEqual(row.staff_override_warning_codes, ["over_capacity"])

    def test_patch_denied_roles(self) -> None:
        get_org_settings(self.org)
        before = self._row(self.org)
        for user in (self.staff, self.promoter, self.member):
            with self.subTest(user=user.username):
                response = self._patch(
                    user,
                    {
                        "staff_override_policy": "block",
                        "staff_override_warning_codes": [],
                    },
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["code"], "not_permitted")
        after = self._row(self.org)
        self.assertEqual(after.staff_override_policy, "silent")
        self.assertEqual(after.staff_override_warning_codes, ALL_CODES)
        self.assertEqual(after.updated_at, before.updated_at)

    def test_patch_validation(self) -> None:
        response = self._patch(self.admin, {"staff_override_warning_codes": ["nope"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Unknown warning code(s): nope",
            str(response.data["staff_override_warning_codes"][0]),
        )

        response = self._patch(self.admin, {"staff_override_policy": "sometimes"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("staff_override_policy", response.data)

        for bad in ("gate_outside", [1], [{"a": 1}], None):
            with self.subTest(codes=bad):
                response = self._patch(
                    self.admin, {"staff_override_warning_codes": bad}
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("staff_override_warning_codes", response.data)

        self.assertEqual(self._row(self.org).staff_override_warning_codes, ALL_CODES)

        response = self._patch(self.admin, {"staff_override_warning_codes": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["staff_override_warning_codes"], [])
        self.assertEqual(self._row(self.org).staff_override_warning_codes, [])

    def test_patch_retention(self) -> None:
        response = self._patch(self.admin, {"signup_record_retention_days": 365})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["signup_record_retention_days"], 365)
        self.assertEqual(self._row(self.org).signup_record_retention_days, 365)

        for bad, msg in (
            (29, "Retention must be at least 30 days."),
            (36501, "Retention must be at most 36500 days."),
        ):
            with self.subTest(days=bad):
                response = self._patch(
                    self.admin, {"signup_record_retention_days": bad}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"signup_record_retention_days": [msg]})
        self.assertEqual(self._row(self.org).signup_record_retention_days, 365)

        response = self._patch(self.admin, {"signup_record_retention_days": None})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["signup_record_retention_days"])
        self.assertIsNone(self._row(self.org).signup_record_retention_days)

        response = self._patch(self.staff, {"signup_record_retention_days": 90})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self._row(self.org).signup_record_retention_days)

    def test_min_retention_read_only(self) -> None:
        response = self._as(self.admin).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["signup_record_min_retention_days"], 30)

        response = self._patch(self.admin, {"signup_record_min_retention_days": 1})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["signup_record_min_retention_days"], 30)

        with override_settings(SIGNUP_RECORD_MIN_RETENTION_DAYS=60):
            response = self._as(self.admin).get(self.url)
            self.assertEqual(response.data["signup_record_min_retention_days"], 60)
            response = self._patch(self.admin, {"signup_record_retention_days": 59})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.data,
                {
                    "signup_record_retention_days": [
                        "Retention must be at least 60 days."
                    ]
                },
            )

    def test_patch_normalizes(self) -> None:
        response = self._patch(
            self.admin,
            {
                "staff_override_warning_codes": [
                    "over_capacity",
                    "gate_outside",
                    "gate_outside",
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        expected = ["gate_outside", "over_capacity"]
        self.assertEqual(response.data["staff_override_warning_codes"], expected)
        self.assertEqual(self._row(self.org).staff_override_warning_codes, expected)

    def test_patch_partial_policy_only(self) -> None:
        response = self._patch(self.admin, {"staff_override_policy": "block"})
        self.assertEqual(response.status_code, 200)
        row = self._row(self.org)
        self.assertEqual(row.staff_override_policy, "block")
        self.assertEqual(row.staff_override_warning_codes, ALL_CODES)
        self.assertEqual(response.data["staff_override_warning_codes"], ALL_CODES)

    def test_patch_ignores_read_only(self) -> None:
        response = self._patch(
            self.admin,
            {
                "organization": self.other_org.pk,
                "available_warning_codes": [],
                "updated_at": "2000-01-01T00:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"], self.org.pk)
        self.assertEqual(len(response.data["available_warning_codes"]), 6)
        self.assertEqual(self._row(self.org).organization_id, self.org.pk)
        self.assertFalse(
            OrgSettings.objects.nocache().filter(organization=self.other_org).exists()
        )

    def test_patch_accepts_code_added_at_runtime(self) -> None:
        with mock.patch.object(
            settings_constants, "ALL_CODES", [*ALL_CODES, "new_code"]
        ):
            response = self._patch(
                self.admin, {"staff_override_warning_codes": ["new_code"]}
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(
                response.data["staff_override_warning_codes"], ["new_code"]
            )
            self.assertEqual(
                response.data["available_warning_codes"][-1],
                {"code": "new_code", "label": "new_code"},
            )
        self.assertEqual(self._row(self.org).staff_override_warning_codes, ["new_code"])

    def test_retired_code_filtered_and_policy_patch_ok(self) -> None:
        row = get_org_settings(self.org)
        OrgSettings.objects.filter(pk=row.pk).update(
            staff_override_warning_codes=[*ALL_CODES, "old_code"]
        )
        invalidate_obj(row)
        self.assertIn(
            "old_code", get_org_settings(self.org).staff_override_warning_codes
        )

        response = self._as(self.admin).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("old_code", response.data["staff_override_warning_codes"])
        self.assertEqual(response.data["staff_override_warning_codes"], ALL_CODES)

        response = self._patch(
            self.admin,
            {
                "staff_override_policy": "confirm",
                "staff_override_warning_codes": response.data[
                    "staff_override_warning_codes"
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["staff_override_policy"], "confirm")
        self.assertEqual(self._row(self.org).staff_override_policy, "confirm")

        response = self._patch(self.admin, {"staff_override_policy": "block"})
        self.assertEqual(response.status_code, 200, response.data)


ADMIN_CHANGELIST_URL = "/admin/org/orgsettings/"
ADMIN_ADD_URL = "/admin/org/orgsettings/add/"


def admin_change_url(pk: int) -> str:
    return f"/admin/org/orgsettings/{pk}/change/"


class OrgSettingsAdminTest(TestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="settings_admin", password="x", email="sa@example.com"
        )
        self.client.force_login(self.superuser)
        self.org = Organization.objects.create(name="Admin Settings Org")
        self.other_org = Organization.objects.create(name="Other Settings Org")

    def _post_change(self, row: OrgSettings, data: dict[str, Any]) -> Any:
        return self.client.post(admin_change_url(row.pk), {**data, "_save": "Save"})

    def test_changelist_and_change_view_load(self) -> None:
        row = get_org_settings(self.org)
        self.assertEqual(self.client.get(ADMIN_CHANGELIST_URL).status_code, 200)
        self.assertEqual(self.client.get(admin_change_url(row.pk)).status_code, 200)

    def test_admin_change_routes_through_service(self) -> None:
        row = get_org_settings(self.org)
        with (
            mock.patch("app.cache_utils._cacheops_invalidate_obj") as invalidate,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self._post_change(
                row,
                {
                    "staff_override_policy": "confirm",
                    "staff_override_warning_codes": '["over_capacity"]',
                },
            )
        self.assertEqual(response.status_code, 302)
        after = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertEqual(after.staff_override_policy, "confirm")
        self.assertEqual(after.staff_override_warning_codes, ["over_capacity"])
        log = OrgLog.objects.get(organization=self.org, action="update")
        self.assertEqual(log.actor, self.superuser)
        self.assertEqual(log.details["area"], "settings")
        self.assertEqual(
            log.details["changed_fields"],
            ["staff_override_policy", "staff_override_warning_codes"],
        )
        invalidate.assert_called_once_with(after)

    def test_admin_add_creates_row(self) -> None:
        with (
            mock.patch("app.cache_utils._cacheops_invalidate_obj") as invalidate,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                ADMIN_ADD_URL,
                {
                    "organization": self.org.pk,
                    "staff_override_policy": "block",
                    "staff_override_warning_codes": (
                        '["over_capacity", "gate_outside", "gate_outside"]'
                    ),
                    "_save": "Save",
                },
            )
        self.assertEqual(response.status_code, 302)
        row = OrgSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.staff_override_policy, "block")
        self.assertEqual(
            row.staff_override_warning_codes, ["gate_outside", "over_capacity"]
        )
        invalidate.assert_called_with(row)
        log = OrgLog.objects.get(organization=self.org, action="update")
        self.assertEqual(log.actor, self.superuser)
        self.assertEqual(
            log.details,
            {
                "area": "settings",
                "changed_fields": [
                    "staff_override_policy",
                    "staff_override_warning_codes",
                ],
            },
        )

    def test_admin_add_defaults_writes_no_audit(self) -> None:
        response = self.client.post(
            ADMIN_ADD_URL,
            {
                "organization": self.org.pk,
                "staff_override_policy": "silent",
                "staff_override_warning_codes": json.dumps(list(ALL_CODES)),
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            OrgSettings.objects.nocache().filter(organization=self.org).exists()
        )
        self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())

    def test_admin_rejects_bad_codes_json(self) -> None:
        row = get_org_settings(self.org)
        for bad in ("null", "{}", '"gate_outside"', '["nope"]', "[1]"):
            with self.subTest(codes=bad):
                response = self._post_change(
                    row,
                    {
                        "staff_override_policy": "confirm",
                        "staff_override_warning_codes": bad,
                    },
                )
                self.assertEqual(response.status_code, 200)
                form = response.context["adminform"].form
                self.assertIn("staff_override_warning_codes", form.errors)
                after = OrgSettings.objects.nocache().get(pk=row.pk)
                self.assertEqual(after.staff_override_policy, "silent")
                self.assertEqual(after.staff_override_warning_codes, list(ALL_CODES))
        self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())

    def test_admin_rejects_low_retention(self) -> None:
        row = get_org_settings(self.org)
        response = self._post_change(
            row,
            {
                "staff_override_policy": "silent",
                "staff_override_warning_codes": json.dumps(list(ALL_CODES)),
                "signup_record_retention_days": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertEqual(
            form.errors["signup_record_retention_days"],
            ["Retention must be at least 30 days."],
        )
        after = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertIsNone(after.signup_record_retention_days)
        self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())

    def test_organization_readonly_on_change(self) -> None:
        row = get_org_settings(self.org)
        response = self._post_change(
            row,
            {
                "organization": self.other_org.pk,
                "staff_override_policy": "confirm",
                "staff_override_warning_codes": "[]",
            },
        )
        self.assertEqual(response.status_code, 302)
        after = OrgSettings.objects.nocache().get(pk=row.pk)
        self.assertEqual(after.organization_id, self.org.pk)
        self.assertEqual(after.staff_override_warning_codes, [])
        self.assertFalse(
            OrgSettings.objects.nocache().filter(organization=self.other_org).exists()
        )

    def test_delete_disabled(self) -> None:
        row = get_org_settings(self.org)
        response = self.client.get(f"/admin/org/orgsettings/{row.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        changelist = self.client.get(ADMIN_CHANGELIST_URL)
        self.assertEqual(changelist.status_code, 200)
        self.assertNotContains(changelist, "delete_selected")
        self.assertTrue(OrgSettings.objects.nocache().filter(pk=row.pk).exists())


class OrgSettingsInertTest(SimpleTestCase):
    FORBIDDEN: tuple[str, ...] = (
        "org.settings_service",
        "org.models_settings",
        "OrgSettings",
        "staff_override_policy",
        "staff_override_warning_codes",
    )
    # Override contract and its callers; codes outside ALL_CODES ignore the policy.
    CONTRACT: frozenset[str] = frozenset(
        {
            "events/overrides.py",
            "events/tests/test_overrides.py",
            "tournament/services/team_management.py",
            "tournament/tests/test_team_management.py",
        }
    )

    # #499 retention purge reads each org's signup_record_retention_days.
    RETENTION: frozenset[str] = frozenset(
        {
            "events/ledger.py",
            "events/tests/test_purge_expired_signup_records.py",
            "events/tests/test_signup_records_purge_task.py",
        }
    )

    def test_policy_inert_until_524(self) -> None:
        """#524 removes this test and replaces it with block/confirm enforcement tests."""
        base = Path(settings.BASE_DIR)
        offenders: list[str] = []
        for path in base.rglob("*.py"):
            parts = path.relative_to(base).parts
            if parts[0] in ("org", "tests") or "migrations" in parts:
                continue
            if "/".join(parts) in self.CONTRACT | self.RETENTION:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            offenders.extend(
                f"{path.relative_to(base)}: {token}"
                for token in self.FORBIDDEN
                if token in text
            )
        self.assertEqual(offenders, [])
