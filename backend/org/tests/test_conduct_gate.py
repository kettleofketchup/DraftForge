from django.test import override_settings

from org.conduct.gate import GATE_OFF, conduct_gate, get_conduct_settings
from org.models_conduct import OrgConductSettings
from org.tests.conduct_base import ConductTestCase


@override_settings(CACHEOPS_ENABLED=False)
class ConductGateTest(ConductTestCase):
    def test_get_settings_does_not_insert(self) -> None:
        settings = get_conduct_settings(self.org)
        self.assertIsNone(settings.pk)
        self.assertEqual(settings.organization_id, self.org.pk)
        self.assertEqual(OrgConductSettings.objects.count(), 0)

    def test_get_settings_create_inserts_once(self) -> None:
        first = get_conduct_settings(self.org, create=True)
        second = get_conduct_settings(self.org.pk, create=True)
        self.assertIsNotNone(first.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(OrgConductSettings.objects.count(), 1)

    def test_get_settings_returns_stored_row(self) -> None:
        stored = OrgConductSettings.objects.create(
            organization=self.org, late_cancel_hours=5
        )
        settings = get_conduct_settings(self.org)
        self.assertEqual(settings.pk, stored.pk)
        self.assertEqual(settings.late_cancel_hours, 5)

    def test_gate_locked_one_query(self) -> None:
        with self.assertNumQueries(1):
            gate = conduct_gate(self.org)
        self.assertIs(gate.feature_on, False)
        self.assertIsNone(gate.settings)
        self.assertIs(gate.enforcement_active, False)
        self.assertEqual(gate.org_id, self.org.pk)

    def test_gate_unlocked_toggles_off_two_queries(self) -> None:
        self.unlock()
        with self.assertNumQueries(2):
            gate = conduct_gate(self.org)
        self.assertIs(gate.feature_on, True)
        self.assertIsNotNone(gate.settings)
        self.assertIs(gate.enforcement_active, False)
        self.assertIs(gate.back_of_line, False)

    def test_gate_enforcement_active_when_any_toggle(self) -> None:
        self.unlock()
        OrgConductSettings.objects.create(organization=self.org, block_enabled=True)
        gate = conduct_gate(self.org.pk)
        self.assertIs(gate.enforcement_active, True)
        self.assertIs(gate.back_of_line, False)

    def test_gate_back_of_line_when_enabled(self) -> None:
        self.unlock()
        OrgConductSettings.objects.create(
            organization=self.org, back_of_line_enabled=True
        )
        gate = conduct_gate(self.org)
        self.assertIs(gate.enforcement_active, True)
        self.assertIs(gate.back_of_line, True)

    def test_gate_locked_ignores_stored_toggles(self) -> None:
        OrgConductSettings.objects.create(
            organization=self.org, back_of_line_enabled=True
        )
        gate = conduct_gate(self.org)
        self.assertIs(gate.enforcement_active, False)
        self.assertIs(gate.back_of_line, False)

    def test_gate_none_is_off_without_queries(self) -> None:
        with self.assertNumQueries(0):
            self.assertIs(conduct_gate(None), GATE_OFF)
