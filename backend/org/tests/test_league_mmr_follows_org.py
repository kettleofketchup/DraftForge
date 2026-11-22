import itertools

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, PositionsModel
from common.game import GameType
from league.models import League, LeagueUser
from org.mmr import bulk_set_org_mmrs, set_org_mmr
from org.models import Organization, OrgUser, OrgUserGameMmr
from user.tests.test_cacheops_integration import _redis_reachable

_discord_ids = itertools.count(930_000_000_000_000_000)
_steam_league_ids = itertools.count(881_000)


def _user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class FollowFixture:
    owner: CustomUser
    member: CustomUser
    org: Organization
    other_org: Organization
    org_user: OrgUser
    other_org_user: OrgUser
    league: League
    pinned_league: League
    other_league: League
    league_user: LeagueUser
    pinned_user: LeagueUser
    other_user: LeagueUser

    def build(self) -> None:
        self.owner = _user("lf_owner")
        self.member = _user("lf_member")
        self.org = Organization.objects.create(name="Follow Org", owner=self.owner)
        self.other_org = Organization.objects.create(
            name="Other Follow Org", owner=self.owner
        )
        self.org_user = OrgUser.objects.create(user=self.member, organization=self.org)
        self.other_org_user = OrgUser.objects.create(
            user=self.member, organization=self.other_org
        )
        OrgUserGameMmr.objects.create(
            org_user=self.org_user, game_type=GameType.DOTA2, mmr=3000
        )
        OrgUserGameMmr.objects.create(
            org_user=self.other_org_user, game_type=GameType.DOTA2, mmr=3000
        )
        self.league = self._league("Follow League", self.org)
        self.pinned_league = self._league("Pinned League", self.org)
        self.other_league = self._league("Other League", self.other_org)
        self.league_user = LeagueUser.objects.create(
            user=self.member, org_user=self.org_user, league=self.league, mmr=3000
        )
        self.pinned_user = LeagueUser.objects.create(
            user=self.member,
            org_user=self.org_user,
            league=self.pinned_league,
            mmr=3300,
            mmr_verified_at=timezone.now(),
            mmr_verified_by=self.owner,
        )
        self.other_user = LeagueUser.objects.create(
            user=self.member,
            org_user=self.other_org_user,
            league=self.other_league,
            mmr=3000,
        )

    def _league(self, name: str, org: Organization) -> League:
        return League.objects.create(
            name=name, organization=org, steam_league_id=next(_steam_league_ids)
        )

    def league_mmr(self, row: LeagueUser) -> int:
        return LeagueUser.objects.nocache().get(pk=row.pk).mmr


class LeagueMmrFollowsOrgTests(FollowFixture, TestCase):
    def setUp(self) -> None:
        self.build()
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def patch(self, game_mmrs: dict[str, int | None]) -> None:
        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/",
            {"game_mmrs": game_mmrs},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_org_patch_resyncs_unverified_league_mmr(self) -> None:
        with capture_logs() as logs:
            self.patch({str(int(GameType.DOTA2)): 4200})
        self.assertEqual(self.league_mmr(self.league_user), 4200)
        synced = [e for e in logs if e["event"] == "league_mmr_synced_from_org"]
        self.assertEqual(len(synced), 1)
        self.assertEqual(synced[0]["system"], "league")
        self.assertEqual(synced[0]["subsystem"], "mmr")
        self.assertEqual(synced[0]["league_user_ids"], [self.league_user.pk])

    def test_org_patch_leaves_official_league_mmr_pinned(self) -> None:
        self.patch({str(int(GameType.DOTA2)): 4200})
        pinned = LeagueUser.objects.nocache().get(pk=self.pinned_user.pk)
        self.assertEqual(pinned.mmr, 3300)
        self.assertIsNotNone(pinned.mmr_verified_at)

    def test_org_patch_leaves_other_org_leagues_untouched(self) -> None:
        self.patch({str(int(GameType.DOTA2)): 4200})
        self.assertEqual(self.league_mmr(self.other_user), 3000)

    def test_org_patch_clearing_mmr_zeroes_league_mmr(self) -> None:
        self.patch({str(int(GameType.DOTA2)): None})
        self.assertEqual(self.league_mmr(self.league_user), 0)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)

    def test_non_league_game_does_not_touch_league_mmr(self) -> None:
        self.patch({str(int(GameType.DEADLOCK)): 2500})
        self.assertEqual(self.league_mmr(self.league_user), 3000)

    def test_set_org_mmr_unchanged_value_skips_sync(self) -> None:
        LeagueUser.objects.filter(pk=self.league_user.pk).update(mmr=1234)
        with capture_logs() as logs:
            set_org_mmr(self.org_user, GameType.DOTA2, 3000, mark_verified=False)
        self.assertEqual(self.league_mmr(self.league_user), 1234)
        self.assertFalse(
            [e for e in logs if e["event"] == "league_mmr_synced_from_org"]
        )

    def test_bulk_set_org_mmrs_resyncs_unverified_league_mmr(self) -> None:
        bulk_set_org_mmrs(self.org.pk, GameType.DOTA2, {self.member.pk: 5100})
        self.assertEqual(self.league_mmr(self.league_user), 5100)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)
        self.assertEqual(self.league_mmr(self.other_user), 3000)

    def test_bulk_set_org_mmrs_clear_zeroes_league_mmr(self) -> None:
        bulk_set_org_mmrs(self.org.pk, GameType.DOTA2, {self.member.pk: None})
        self.assertEqual(self.league_mmr(self.league_user), 0)

    def test_bulk_set_non_league_game_does_not_touch_league_mmr(self) -> None:
        bulk_set_org_mmrs(self.org.pk, GameType.DEADLOCK, {self.member.pk: 2500})
        self.assertEqual(self.league_mmr(self.league_user), 3000)

    def test_csv_import_org_mmr_resyncs_league_mmr(self) -> None:
        response = self.client.post(
            f"/api/organizations/{self.org.pk}/import-csv/",
            {
                "rows": [{"discord_id": self.member.discordId, "mmr": 4700}],
                "update_mmr": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.league_mmr(self.league_user), 4700)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)


class LeagueMmrFollowsOrgCacheTests(FollowFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        self.build()

    def test_set_org_mmr_invalidates_cached_league_user(self) -> None:
        self.assertEqual(LeagueUser.objects.get(pk=self.league_user.pk).mmr, 3000)
        set_org_mmr(self.org_user, GameType.DOTA2, 4400, mark_verified=False)
        self.assertEqual(LeagueUser.objects.get(pk=self.league_user.pk).mmr, 4400)

    def test_bulk_set_org_mmrs_invalidates_cached_league_user(self) -> None:
        self.assertEqual(LeagueUser.objects.get(pk=self.league_user.pk).mmr, 3000)
        bulk_set_org_mmrs(self.org.pk, GameType.DOTA2, {self.member.pk: 4600})
        self.assertEqual(LeagueUser.objects.get(pk=self.league_user.pk).mmr, 4600)
