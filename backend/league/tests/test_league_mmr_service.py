from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from app.models import CustomUser, PositionsModel
from league.mmr import merge_league_users, set_league_mmr
from league.models import League, LeagueLog, LeagueUser
from org.models import MmrChangeRequest, Organization, OrgLog, OrgUser
from org.tests.mmr_request_mixin import MmrRequestTestMixin
from tournament.views.csv_import import _update_mmr_for_target
from user.tests.test_cacheops_integration import _redis_reachable


def _user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name, positions=PositionsModel.objects.create()
    )


class LeagueMmrFixture:
    staff: CustomUser
    member: CustomUser
    org: Organization
    league: League
    org_user: OrgUser
    league_user: LeagueUser

    def build(self) -> None:
        self.staff = _user("lm_staff")
        self.member = _user("lm_member")
        self.org = Organization.objects.create(name="League Mmr Org", owner=self.staff)
        self.league = League.objects.create(
            name="League Mmr League", organization=self.org, steam_league_id=777001
        )
        self.org_user = OrgUser.objects.create(user=self.member, organization=self.org)
        self.league_user = LeagueUser.objects.create(
            user=self.member, org_user=self.org_user, league=self.league, mmr=3000
        )

    def fresh(self) -> LeagueUser:
        return LeagueUser.objects.nocache().get(pk=self.league_user.pk)

    def stamp(self) -> None:
        LeagueUser.objects.filter(pk=self.league_user.pk).update(
            mmr_verified_at=timezone.now(), mmr_verified_by=self.staff
        )
        self.league_user = self.fresh()


class SetLeagueMmrTests(LeagueMmrFixture, MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_set_league_mmr_writes_marker_and_logs(self) -> None:
        result = set_league_mmr(
            self.league_user,
            4500,
            actor=self.staff,
            verified=True,
            source="mmr_request",
            request_id=77,
        )

        row = self.fresh()
        self.assertEqual(row.mmr, 4500)
        self.assertIsNotNone(row.mmr_verified_at)
        self.assertEqual(row.mmr_verified_by_id, self.staff.pk)
        self.assertTrue(result.verified)
        self.assertEqual(result.previous, 3000)
        league_log = LeagueLog.objects.get(action="set_mmr")
        self.assertEqual(league_log.league_id, self.league.pk)
        self.assertEqual(league_log.actor_id, self.staff.pk)
        self.assertEqual(league_log.target_user_id, self.member.pk)
        self.assertEqual(league_log.details["source"], "mmr_request")
        self.assertEqual(league_log.details["request_id"], 77)
        self.assertEqual(league_log.details["previous_mmr"], 3000)
        org_log = OrgLog.objects.get(action="set_mmr")
        self.assertEqual(org_log.organization_id, self.org.pk)
        self.assertEqual(org_log.details["source"], "mmr_request")
        self.assertEqual(org_log.details["league_id"], self.league.pk)
        self.assertEqual(org_log.details["request_id"], 77)

    def test_set_league_mmr_self_unverified(self) -> None:
        self.stamp()
        result = set_league_mmr(
            self.league_user,
            4100,
            actor=self.member,
            verified=True,
            source="staff_set",
        )

        row = self.fresh()
        self.assertFalse(result.verified)
        self.assertEqual(row.mmr, 4100)
        self.assertIsNone(row.mmr_verified_at)
        self.assertIsNone(row.mmr_verified_by_id)

    def test_set_league_mmr_zero_clears_marker(self) -> None:
        self.stamp()
        result = set_league_mmr(
            self.league_user, 0, actor=self.staff, verified=True, source="staff_set"
        )

        row = self.fresh()
        self.assertFalse(result.verified)
        self.assertEqual(row.mmr, 0)
        self.assertIsNone(row.mmr_verified_at)

    def test_set_league_mmr_supersedes_pending(self) -> None:
        pending = self.make_request(
            org_user=self.org_user, league_user=self.league_user
        )
        kept = self.make_request(
            org_user=self.org_user,
            league_user=self.league_user,
            status=MmrChangeRequest.Status.APPROVED,
        )

        result = set_league_mmr(
            self.league_user,
            4200,
            actor=self.staff,
            verified=True,
            source="staff_set",
        )

        self.assertEqual(result.superseded_ids, [pending.pk])
        pending.refresh_from_db()
        self.assertEqual(pending.status, MmrChangeRequest.Status.SUPERSEDED)
        self.assertEqual(pending.reviewed_by_id, self.staff.pk)
        self.assertEqual(pending.approved_mmr, 4200)
        kept.refresh_from_db()
        self.assertEqual(kept.status, MmrChangeRequest.Status.APPROVED)

    def test_set_league_mmr_excludes_passed_request(self) -> None:
        pending = self.make_request(
            org_user=self.org_user, league_user=self.league_user
        )

        result = set_league_mmr(
            self.league_user,
            4200,
            actor=self.staff,
            verified=True,
            source="mmr_request",
            request_id=pending.pk,
        )

        self.assertEqual(result.superseded_ids, [])
        pending.refresh_from_db()
        self.assertEqual(pending.status, MmrChangeRequest.Status.PENDING)

    def test_set_league_mmr_unverified_keeps_pending(self) -> None:
        pending = self.make_request(
            org_user=self.org_user, league_user=self.league_user
        )

        set_league_mmr(
            self.league_user, 4200, actor=self.staff, verified=False, source="x"
        )

        pending.refresh_from_db()
        self.assertEqual(pending.status, MmrChangeRequest.Status.PENDING)

    def test_csv_league_overwrite_clears_marker(self) -> None:
        self.stamp()
        _update_mmr_for_target(self.member, self.org, self.league, "league", 4321, {})

        row = self.fresh()
        self.assertEqual(row.mmr, 4321)
        self.assertIsNone(row.mmr_verified_at)
        self.assertIsNone(row.mmr_verified_by_id)

    def test_claim_merge_league_prefers_verified(self) -> None:
        other = _user("lm_other")
        other_ou = OrgUser.objects.create(user=other, organization=self.org)
        loser = LeagueUser.objects.create(
            user=other,
            org_user=other_ou,
            league=self.league,
            mmr=2000,
            mmr_verified_at=timezone.now(),
            mmr_verified_by=self.staff,
        )

        merge_league_users(loser, self.league_user)

        row = self.fresh()
        self.assertEqual(row.mmr, 2000)
        self.assertIsNotNone(row.mmr_verified_at)
        self.assertEqual(row.mmr_verified_by_id, self.staff.pk)

    def test_merge_league_users_keeps_verified_keeper(self) -> None:
        self.stamp()
        other = _user("lm_other")
        other_ou = OrgUser.objects.create(user=other, organization=self.org)
        loser = LeagueUser.objects.create(
            user=other, org_user=other_ou, league=self.league, mmr=9000
        )

        merge_league_users(loser, self.league_user)

        row = self.fresh()
        self.assertEqual(row.mmr, 3000)
        self.assertIsNotNone(row.mmr_verified_at)

    def test_merge_league_users_neither_verified_keeps_higher(self) -> None:
        other = _user("lm_other")
        other_ou = OrgUser.objects.create(user=other, organization=self.org)
        loser = LeagueUser.objects.create(
            user=other, org_user=other_ou, league=self.league, mmr=6000
        )

        merge_league_users(loser, self.league_user)

        row = self.fresh()
        self.assertEqual(row.mmr, 6000)
        self.assertIsNone(row.mmr_verified_at)


class SetLeagueMmrCacheTests(LeagueMmrFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()
        self.build()

    def test_set_league_mmr_invalidates_cache(self) -> None:
        self.assertEqual(LeagueUser.objects.get(pk=self.league_user.pk).mmr, 3000)
        self.assertIsNone(
            LeagueUser.objects.get(pk=self.league_user.pk).mmr_verified_at
        )

        set_league_mmr(
            self.league_user, 4800, actor=self.staff, verified=True, source="x"
        )

        cached = LeagueUser.objects.get(pk=self.league_user.pk)
        self.assertEqual(cached.mmr, 4800)
        self.assertIsNotNone(cached.mmr_verified_at)
