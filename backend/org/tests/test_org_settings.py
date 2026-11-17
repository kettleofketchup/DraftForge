from django.test import SimpleTestCase

from org import settings_constants
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
