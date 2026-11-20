from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone as tz

from app.models import OrgLog
from events.serializers import EventSerializer
from org.conduct.constants import Outcome, OutcomeSource
from org.feature_keys import FeatureKey
from org.models import OrgConductSettings
from org.models_conduct import AttendanceOutcome
from org.tests.conduct_base import ConductTestCase


class AttendanceOutcomeModelTest(ConductTestCase):
    def test_unique_per_event_member(self) -> None:
        event = self.make_event()
        user = self.make_user()
        self.outcome(user, event=event)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.outcome(user, event=event)

    def test_unique_ignores_null_event(self) -> None:
        user = self.make_user()
        self.outcome(user)
        self.outcome(user)
        self.assertEqual(
            AttendanceOutcome.objects.nocache()
            .filter(org_user__user=user, event__isnull=True)
            .count(),
            2,
        )

    def test_staff_source_requires_reason(self) -> None:
        user = self.make_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.outcome(user, event=self.make_event(), source=OutcomeSource.STAFF)
        row = self.outcome(
            user, event=self.make_event(), source=OutcomeSource.STAFF, reason="late"
        )
        self.assertEqual(row.reason, "late")

    def test_counted_excludes_walkins_pending_voided_unfinalized_excused(
        self,
    ) -> None:
        user = self.make_user()
        self.outcome(user, event=self.make_event())
        self.outcome(user, event=self.make_event(), committed=False)
        self.outcome(user, event=self.make_event(), outcome=Outcome.PENDING)
        self.outcome(user, event=self.make_event(), voided_at=tz.now())
        self.outcome(user, event=self.make_event(), finalized=False)
        self.outcome(user, event=self.make_event(), outcome=Outcome.EXCUSED)
        self.assertEqual(AttendanceOutcome.objects.nocache().counted().count(), 1)

    def test_for_event(self) -> None:
        event = self.make_event()
        self.outcome(self.make_user(), event=event)
        self.outcome(self.make_user(), event=self.make_event())
        self.assertEqual(
            AttendanceOutcome.objects.nocache().for_event(event.pk).count(), 1
        )

    def test_event_delete_keeps_row(self) -> None:
        event = self.make_event(name="Gone Night")
        row = self.outcome(self.make_user(), event=event)
        event.delete()
        row = AttendanceOutcome.objects.nocache().get(pk=row.pk)
        self.assertIsNone(row.event_id)
        self.assertEqual(row.event_name, "Gone Night")

    def test_user_delete_cascades(self) -> None:
        user = self.make_user()
        row = self.outcome(user, event=self.make_event())
        user.delete()
        self.assertFalse(AttendanceOutcome.objects.nocache().filter(pk=row.pk).exists())


class OrgConductSettingsModelTest(ConductTestCase):
    def test_settings_defaults(self) -> None:
        s = OrgConductSettings(organization=self.org)
        self.assertEqual(s.late_cancel_hours, 2)
        self.assertEqual(s.late_cancel_weight, Decimal("0.50"))
        self.assertEqual(s.half_life_days, 90)
        self.assertEqual(s.max_age_days, 365)
        self.assertEqual(s.prior_show_rate, Decimal("0.85"))
        self.assertEqual(s.prior_strength, Decimal("3.00"))
        self.assertEqual(s.min_events, 3)
        self.assertIs(s.leaderboard_public, True)
        self.assertIs(s.back_of_line_enabled, False)
        self.assertEqual(s.back_of_line_below, Decimal("0.75"))
        self.assertIs(s.require_approval_enabled, False)
        self.assertEqual(s.require_approval_below, Decimal("0.65"))
        self.assertIs(s.block_enabled, False)
        self.assertEqual(s.block_below, Decimal("0.40"))
        self.assertIs(s.enforce_on_new_members, False)
        self.assertIsNone(s.updated_by_id)

    def test_settings_save_and_reverse_accessor(self) -> None:
        OrgConductSettings.objects.create(organization=self.org)
        self.org.refresh_from_db()
        self.assertEqual(self.org.conduct_settings.min_events, 3)


class ConductWiringTest(ConductTestCase):
    def test_conduct_feature_key(self) -> None:
        self.assertIs(FeatureKey("conduct"), FeatureKey.CONDUCT)

    def test_event_serializer_conduct_finalized_at_read_only(self) -> None:
        self.assertIn("conduct_finalized_at", EventSerializer.Meta.fields)
        self.assertIn("conduct_finalized_at", EventSerializer.Meta.read_only_fields)

    def test_orglog_actions(self) -> None:
        self.assertLessEqual(
            {"set_attendance", "finalize_attendance", "void_attendance"},
            {a for a, _ in OrgLog.ACTION_CHOICES},
        )
