from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization
from events.models import Event
from org.contributions.kinds import DEFAULT_POINTS, ContributionKind
from org.contributions.points import points_for
from org.models import ContributionEntry, ContributionPointValue, OrgUser


class ContributionModelsTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="ledger_admin", password="x"
        )
        self.member = CustomUser.objects.create_user(
            username="ledger_member", password="x"
        )
        self.org = Organization.objects.create(name="Ledger Org", owner=self.admin)
        self.league = League.objects.create(
            name="Ledger League", organization=self.org, steam_league_id=99881
        )
        self.org_user = OrgUser.objects.create(user=self.member, organization=self.org)
        self.event = Event.objects.create(
            organization=self.org,
            name="Ledger Event",
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            tournament_league=self.league,
        )

    def _entry(self, **overrides: object) -> ContributionEntry:
        fields: dict[str, object] = {
            "org_user": self.org_user,
            "organization": self.org,
            "kind": ContributionKind.EVENT_HOST,
            "points": 10,
            "event": self.event,
            "event_name": self.event.name,
            "occurred_at": timezone.now(),
        }
        fields.update(overrides)
        return ContributionEntry.objects.create(**fields)

    def test_points_for_default_and_override(self) -> None:
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HOST), 10)
        self.assertEqual(
            points_for(self.org, ContributionKind.PROMO_MESSAGE),
            DEFAULT_POINTS["promo_message"],
        )
        ContributionPointValue.objects.create(
            organization=self.org, kind=ContributionKind.EVENT_HOST, points=25
        )
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HOST), 25)
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HELPER), 5)

    def test_duplicate_event_staff_entry_rejected(self) -> None:
        self._entry()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._entry()

    def test_points_for_unrated_kind_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            points_for(self.org, ContributionKind.MANUAL)
        with self.assertRaises(ValueError):
            points_for(self.org, "bogus")

    def test_duplicate_event_helper_entry_rejected(self) -> None:
        self._entry(kind=ContributionKind.EVENT_HELPER, points=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._entry(kind=ContributionKind.EVENT_HELPER, points=5)

    def test_host_and_helper_same_event_allowed(self) -> None:
        self._entry()
        self._entry(kind=ContributionKind.EVENT_HELPER, points=5)
        self.assertEqual(ContributionEntry.objects.count(), 2)

    def test_two_manual_entries_same_event_allowed(self) -> None:
        self._entry(kind=ContributionKind.MANUAL, points=3, reason="setup")
        self._entry(kind=ContributionKind.MANUAL, points=4, reason="teardown")
        self.assertEqual(
            ContributionEntry.objects.filter(kind=ContributionKind.MANUAL).count(), 2
        )

    def test_bare_orguser_delete_restricted(self) -> None:
        self._entry()
        with self.assertRaises(RestrictedError):
            self.org_user.delete()

    def test_org_delete_cascades_ledger(self) -> None:
        self._entry()
        self.org.delete()
        self.assertFalse(ContributionEntry.objects.exists())

    def test_event_delete_keeps_entry(self) -> None:
        entry = self._entry()
        self.event.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.event)
        self.assertEqual(entry.event_name, "Ledger Event")
