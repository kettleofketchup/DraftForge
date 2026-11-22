from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from app.models import CustomUser, League
from events.models import Event
from org.contributions.kinds import EVENT_STAFF_KINDS, ContributionKind
from org.models import ContributionEntry, ContributionPointValue, Organization, OrgUser
from org.standing import ledger
from org.standing.kinds import (
    ONCE_PER_EVENT_KINDS,
    LedgerKind,
    build_kinds,
    kinds_for,
)
from org.standing.ledger import points_for
from org.standing.periods import parse_period

OCT_10 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
NOV_5 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


class LedgerKindsTest(SimpleTestCase):
    def test_build_kinds_rejects_duplicate(self) -> None:
        kind = LedgerKind(track="contribution", default_points=1, once_per_event=False)
        with self.assertRaises(ValueError):
            build_kinds([("x", kind)], [("x", kind)])

    def test_contribution_kinds(self) -> None:
        self.assertEqual(
            kinds_for("contribution"),
            {"promo_message", "event_host", "event_helper", "manual"},
        )

    def test_once_per_event_matches_staff_kinds(self) -> None:
        self.assertEqual(
            ONCE_PER_EVENT_KINDS & kinds_for("contribution"),
            {k.value for k in EVENT_STAFF_KINDS},
        )


class LedgerTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="lg_owner", password="x")
        self.alice = CustomUser.objects.create_user(username="lg_alice", password="x")
        self.bob = CustomUser.objects.create_user(username="lg_bob", password="x")
        self.carol = CustomUser.objects.create_user(username="lg_carol", password="x")
        self.org = Organization.objects.create(name="Ledger Helpers", owner=self.owner)
        self.other_org = Organization.objects.create(
            name="Ledger Helpers Other", owner=self.owner
        )
        league = League.objects.create(
            name="Ledger Helpers League", organization=self.org, steam_league_id=99671
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Ledger Helpers Event",
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.owner,
            tournament_league=league,
        )
        self.other_event = Event.objects.create(
            organization=self.org,
            name="Ledger Helpers Event 2",
            scheduled_at=timezone.now() + timedelta(days=2),
            created_by=self.owner,
            tournament_league=league,
        )

    def _award(
        self,
        user: CustomUser,
        points: int,
        occurred_at: datetime = NOV_5,
        *,
        kind: str = ContributionKind.MANUAL,
        org: Organization | None = None,
        event: Event | None = None,
    ) -> ContributionEntry:
        return ledger.award(
            org=org or self.org,
            user=user,
            kind=kind,
            occurred_at=occurred_at,
            points=points,
            event=event,
        )

    def test_points_for_default_and_override(self) -> None:
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HOST), 10)
        ContributionPointValue.objects.create(
            organization=self.org, kind=ContributionKind.EVENT_HOST, points=20
        )
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HOST), 20)
        with self.assertRaisesMessage(ValueError, "no default points for kind"):
            points_for(self.org, ContributionKind.MANUAL)
        with self.assertRaisesMessage(ValueError, "no default points for kind"):
            points_for(self.org, "nope")

    def test_award_unknown_kind_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._award(self.alice, 3, kind="nope")
        self.assertFalse(ContributionEntry.objects.exists())
        self.assertFalse(OrgUser.objects.filter(user=self.alice).exists())

    def test_award_creates_member_and_row(self) -> None:
        entry = ledger.award(
            org=self.org,
            user=self.alice,
            kind=ContributionKind.EVENT_HOST,
            occurred_at=NOV_5,
            event=self.event,
        )
        org_user = OrgUser.objects.get(user=self.alice, organization=self.org)
        self.assertEqual(entry.org_user_id, org_user.pk)
        self.assertEqual(entry.points, 10)
        self.assertEqual(entry.event_name, self.event.name)
        self.assertEqual(entry.kind, "event_host")

    def test_award_without_event_has_blank_event_name(self) -> None:
        entry = self._award(self.alice, 4)
        self.assertEqual(entry.event_name, "")
        self.assertIsNone(entry.event_id)

    def test_sum_by_member_drops_zero_totals_and_orders(self) -> None:
        self._award(self.bob, 5)
        self._award(self.alice, 5)
        self._award(self.carol, 7)
        zero = self._award(self.owner, 3)
        ContributionEntry.objects.filter(pk=zero.pk).update(points=0)
        self._award(self.carol, 50, org=self.other_org)
        rows = list(
            ledger.sum_by_member(
                self.org.pk, track="contribution", period=parse_period(self.org, None)
            )
        )
        members = {
            ou.pk: ou.user.username
            for ou in OrgUser.objects.select_related("user").filter(
                organization=self.org
            )
        }
        self.assertEqual(
            [(members[r["org_user"]], r["total"], r["entries"]) for r in rows],
            [("lg_carol", 7, 1), ("lg_alice", 5, 1), ("lg_bob", 5, 1)],
        )

    def test_total_respects_period(self) -> None:
        self._award(self.alice, 10, OCT_10)
        self._award(self.bob, 3, NOV_5)
        self._award(self.carol, 99, NOV_5, org=self.other_org)
        self.assertEqual(
            ledger.total(
                self.org.pk, track="contribution", period=parse_period(self.org, None)
            ),
            13,
        )
        self.assertEqual(
            ledger.total(
                self.org.pk,
                track="contribution",
                period=parse_period(self.org, "2026-11"),
            ),
            3,
        )
        self.assertEqual(
            ledger.total(
                self.org.pk,
                track="contribution",
                period=parse_period(self.org, "2026-09"),
            ),
            0,
        )

    def test_revoke_event_kinds_keeps_other_kinds_and_events(self) -> None:
        self._award(self.alice, 10, kind=ContributionKind.EVENT_HOST, event=self.event)
        self._award(self.bob, 5, kind=ContributionKind.EVENT_HELPER, event=self.event)
        manual = self._award(self.carol, 2, event=self.event)
        other = self._award(
            self.alice, 10, kind=ContributionKind.EVENT_HOST, event=self.other_event
        )
        deleted = ledger.revoke_event_kinds(self.event, kinds=EVENT_STAFF_KINDS)
        self.assertEqual(deleted, 2)
        self.assertEqual(
            set(ContributionEntry.objects.values_list("pk", flat=True)),
            {manual.pk, other.pk},
        )
