from types import SimpleNamespace

from django.test import SimpleTestCase

import events.constants
import events.services
from org.conduct.constants import (
    COUNTED,
    STAFF_SETTABLE,
    TIER_SEVERITY,
    Outcome,
    Tier,
    expected_statuses,
)


class ConductConstantsTest(SimpleTestCase):
    def test_expected_statuses_auto_approve(self) -> None:
        self.assertEqual(
            expected_statuses(SimpleNamespace(auto_approve=True)),
            frozenset({"approved", "confirmed"}),
        )

    def test_expected_statuses_manual_approval_adds_rsvp(self) -> None:
        self.assertEqual(
            expected_statuses(SimpleNamespace(auto_approve=False)),
            frozenset({"approved", "confirmed", "rsvp"}),
        )

    def test_counted_is_subset_of_staff_settable(self) -> None:
        self.assertTrue(set(COUNTED) <= set(STAFF_SETTABLE))
        self.assertNotIn(Outcome.EXCUSED, COUNTED)

    def test_registered_statuses_reexported_from_services(self) -> None:
        self.assertIs(
            events.services.REGISTERED_SIGNUP_STATUSES,
            events.constants.REGISTERED_SIGNUP_STATUSES,
        )

    def test_tier_severity_orders_block_strictest(self) -> None:
        self.assertEqual(max(Tier, key=TIER_SEVERITY.__getitem__), Tier.BLOCK)
