from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from app.models import Organization
from org import settings_constants
from org.models import OrgSettings
from org.settings_constants import StaffOverridePolicy

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
