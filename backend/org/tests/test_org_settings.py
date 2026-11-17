from collections.abc import Callable
from typing import Any
from unittest import mock

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase

from app.models import CustomUser, Organization, OrgLog
from org import settings_constants, settings_service
from org.models import OrgSettings
from org.settings_constants import ALL_CODES, StaffOverridePolicy
from org.settings_service import (
    get_org_settings,
    normalize_warning_codes,
    update_org_settings,
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
        )

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
