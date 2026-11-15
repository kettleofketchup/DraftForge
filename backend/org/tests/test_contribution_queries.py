from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.periods import parse_period
from org.contributions.queries import (
    MAX_MONTHS,
    leaderboard,
    member_entries,
    member_monthly,
    member_totals,
    org_total,
)
from org.contributions.services import award_entry
from org.models import ContributionEntry, OrgUser

NY = ZoneInfo("America/New_York")
OCT31_11PM_NY = datetime(2026, 10, 31, 23, 0, tzinfo=NY).astimezone(UTC)
NOV_5 = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class ContributionQueriesTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="q_owner", password="x")
        self.alice = CustomUser.objects.create_user(username="q_alice", password="x")
        self.bob = CustomUser.objects.create_user(username="q_bob", password="x")
        self.carol = CustomUser.objects.create_user(username="q_carol", password="x")
        self.org = Organization.objects.create(
            name="Queries Org", owner=self.owner, timezone="America/New_York"
        )
        self.other_org = Organization.objects.create(
            name="Queries Other Org", owner=self.owner
        )
        league = League.objects.create(
            name="Queries League", organization=self.org, steam_league_id=99781
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Queries Event",
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.owner,
            tournament_league=league,
        )

    def _award(
        self,
        user: CustomUser,
        points: int,
        occurred_at: datetime,
        org: Organization | None = None,
        kind: str = ContributionKind.MANUAL,
        event: Event | None = None,
    ) -> ContributionEntry:
        return award_entry(
            org=org or self.org,
            user=user,
            kind=kind,
            occurred_at=occurred_at,
            points=points,
            event=event,
        )

    def _org_user(self, user: CustomUser, org: Organization | None = None) -> OrgUser:
        return OrgUser.objects.get(user=user, organization=org or self.org)

    def _seed(self) -> None:
        self._award(self.alice, 10, OCT31_11PM_NY)
        self._award(self.alice, 5, NOV_5)
        self._award(self.bob, 3, NOV_5)
        self._award(self.bob, 12, NOV_5)
        self._award(self.carol, 100, NOV_5, org=self.other_org)

    def test_org_total_equals_ledger_sum(self) -> None:
        self._seed()
        self.assertEqual(org_total(self.org, parse_period(self.org, None)), 30)
        self.assertEqual(org_total(self.org, parse_period(self.org, "2026-10")), 10)
        self.assertEqual(org_total(self.org, parse_period(self.org, "2026-11")), 20)
        self.assertEqual(org_total(self.org, parse_period(self.org, "2026-09")), 0)

    def test_leaderboard_ranks_by_points_then_username(self) -> None:
        self._seed()
        rows = leaderboard(self.org, parse_period(self.org, None))
        self.assertEqual([r["username"] for r in rows], ["q_alice", "q_bob"])
        self.assertEqual([r["points"] for r in rows], [15, 15])
        self.assertEqual([r["entries"] for r in rows], [2, 2])
        alice = rows[0]
        self.assertEqual(alice["user_pk"], self.alice.pk)
        self.assertEqual(alice["org_user_pk"], self._org_user(self.alice).pk)
        self.assertIn("nickname", alice)
        self.assertIn("avatarUrl", alice)

    def test_leaderboard_period_and_limit(self) -> None:
        self._seed()
        rows = leaderboard(self.org, parse_period(self.org, "2026-11"))
        self.assertEqual(
            [(r["username"], r["points"]) for r in rows],
            [("q_bob", 15), ("q_alice", 5)],
        )
        limited = leaderboard(self.org, parse_period(self.org, "2026-11"), limit=1)
        self.assertEqual([r["username"] for r in limited], ["q_bob"])

    def test_leaderboard_skips_zero_sum_members(self) -> None:
        self._award(self.alice, 0, NOV_5)
        self._award(self.bob, 2, NOV_5)
        rows = leaderboard(self.org, parse_period(self.org, None))
        self.assertEqual([r["username"] for r in rows], ["q_bob"])

    def test_leaderboard_reflects_new_award_with_cache_on(self) -> None:
        self._award(self.alice, 4, NOV_5)
        period = parse_period(self.org, None)
        self.assertEqual(leaderboard(self.org, period)[0]["points"], 4)
        self.assertEqual(org_total(self.org, period), 4)
        self._award(self.alice, 6, NOV_5)
        self._award(self.bob, 1, NOV_5)
        rows = leaderboard(self.org, period)
        self.assertEqual(
            [(r["username"], r["points"]) for r in rows][0], ("q_alice", 10)
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(org_total(self.org, period), 11)
        self.assertEqual(
            member_totals(self._org_user(self.alice), now=NOW)["all_time"], 10
        )

    def test_leaderboard_query_count_and_ledger_uncached(self) -> None:
        self.assertNotIn("org.contributionentry", settings.CACHEOPS)
        self._seed()
        self._award(self.owner, 7, NOV_5)
        period = parse_period(self.org, None)
        with self.assertNumQueries(2):
            rows = leaderboard(self.org, period)
            avatars = [r["avatarUrl"] for r in rows]
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(avatars), 3)

    def test_member_entries_newest_first_within_period(self) -> None:
        older = self._award(self.alice, 10, OCT31_11PM_NY, event=self.event)
        newer = self._award(self.alice, 5, NOV_5)
        ou = self._org_user(self.alice)
        all_time = list(member_entries(ou, parse_period(self.org, None)))
        self.assertEqual([e.pk for e in all_time], [newer.pk, older.pk])
        october = list(member_entries(ou, parse_period(self.org, "2026-10")))
        self.assertEqual([e.pk for e in october], [older.pk])
        with self.assertNumQueries(1):
            entries = list(member_entries(ou, parse_period(self.org, None)))
            names = [e.event.name if e.event else None for e in entries]
        self.assertEqual(names, [None, "Queries Event"])

    def test_member_monthly_buckets_in_org_timezone(self) -> None:
        self._seed()
        months = member_monthly(self._org_user(self.alice), months=3, now=NOW)
        self.assertEqual(
            months,
            [
                {"month": "2026-09", "points": 0},
                {"month": "2026-10", "points": 10},
                {"month": "2026-11", "points": 5},
            ],
        )

    def test_member_monthly_default_twelve_months_across_year(self) -> None:
        self._award(self.alice, 2, datetime(2026, 1, 10, tzinfo=UTC))
        self._award(self.alice, 9, datetime(2025, 11, 10, tzinfo=UTC))
        months = member_monthly(self._org_user(self.alice), now=NOW)
        self.assertEqual(len(months), 12)
        self.assertEqual(months[0], {"month": "2025-12", "points": 0})
        self.assertEqual(months[1], {"month": "2026-01", "points": 2})
        self.assertEqual(months[-1]["month"], "2026-11")

    def test_member_monthly_clamps_months(self) -> None:
        self._award(self.alice, 5, NOV_5)
        ou = self._org_user(self.alice)
        self.assertEqual(
            member_monthly(ou, months=0, now=NOW), [{"month": "2026-11", "points": 5}]
        )
        self.assertEqual(len(member_monthly(ou, months=-3, now=NOW)), 1)
        huge = member_monthly(ou, months=10_000, now=NOW)
        self.assertEqual(len(huge), MAX_MONTHS)
        self.assertEqual(huge[-1], {"month": "2026-11", "points": 5})

    def test_member_totals(self) -> None:
        self._seed()
        self.assertEqual(
            member_totals(self._org_user(self.alice), now=NOW),
            {"all_time": 15, "this_month": 5},
        )
        self.assertEqual(
            member_totals(self._org_user(self.carol, self.other_org), now=NOW),
            {"all_time": 100, "this_month": 100},
        )

    def test_bad_timezone_org_still_works(self) -> None:
        self._seed()
        Organization.objects.filter(pk=self.org.pk).update(timezone="Mars/Base")
        self.org.refresh_from_db()
        ou = self._org_user(self.alice)
        self.assertEqual(org_total(self.org, parse_period(self.org, "2026-11")), 30)
        self.assertEqual(len(leaderboard(self.org, parse_period(self.org, None))), 2)
        self.assertEqual(
            member_monthly(ou, months=2, now=NOW),
            [{"month": "2026-10", "points": 0}, {"month": "2026-11", "points": 15}],
        )
        self.assertEqual(member_totals(ou, now=NOW), {"all_time": 15, "this_month": 15})
