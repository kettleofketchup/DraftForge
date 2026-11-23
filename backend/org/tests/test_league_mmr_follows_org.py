import itertools

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, PositionsModel, Tournament
from common.game import GameType
from league.models import League, LeagueUser
from org.mmr import bulk_set_org_mmrs, set_org_mmr
from org.models import Organization, OrgUser, OrgUserGameMmr
from steam.functions.mmr_calculation import update_user_league_mmr
from steam.functions.stats_update import update_all_league_stats_for_league
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats
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
        synced = [e for e in logs if e["event"] == "league_mmr_recomputed"]
        self.assertEqual(len(synced), 1)
        self.assertEqual(synced[0]["system"], "league")
        self.assertEqual(synced[0]["subsystem"], "mmr")
        self.assertEqual(synced[0]["trigger"], "org_mmr")
        self.assertEqual(synced[0]["league_user_ids"], [self.league_user.pk])

    def test_org_patch_leaves_official_league_mmr_pinned(self) -> None:
        self.patch({str(int(GameType.DOTA2)): 4200})
        pinned = LeagueUser.objects.nocache().get(pk=self.pinned_user.pk)
        self.assertEqual(pinned.mmr, 3300)
        self.assertIsNotNone(pinned.mmr_verified_at)

    def test_org_patch_leaves_other_org_leagues_untouched(self) -> None:
        self.patch({str(int(GameType.DOTA2)): 4200})
        self.assertEqual(self.league_mmr(self.other_user), 3000)

    def test_org_patch_clearing_mmr_leaves_league_mmr(self) -> None:
        self.patch({str(int(GameType.DOTA2)): None})
        self.assertEqual(self.league_mmr(self.league_user), 3000)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)

    def test_non_league_game_does_not_touch_league_mmr(self) -> None:
        self.patch({str(int(GameType.DEADLOCK)): 2500})
        self.assertEqual(self.league_mmr(self.league_user), 3000)

    def test_set_org_mmr_unchanged_value_skips_sync(self) -> None:
        LeagueUser.objects.filter(pk=self.league_user.pk).update(mmr=1234)
        with capture_logs() as logs:
            set_org_mmr(self.org_user, GameType.DOTA2, 3000, mark_verified=False)
        self.assertEqual(self.league_mmr(self.league_user), 1234)
        self.assertFalse([e for e in logs if e["event"] == "league_mmr_recomputed"])

    def test_bulk_set_org_mmrs_resyncs_unverified_league_mmr(self) -> None:
        bulk_set_org_mmrs(self.org.pk, GameType.DOTA2, {self.member.pk: 5100})
        self.assertEqual(self.league_mmr(self.league_user), 5100)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)
        self.assertEqual(self.league_mmr(self.other_user), 3000)

    def test_bulk_set_org_mmrs_clear_leaves_league_mmr(self) -> None:
        bulk_set_org_mmrs(self.org.pk, GameType.DOTA2, {self.member.pk: None})
        self.assertEqual(self.league_mmr(self.league_user), 3000)

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


class LeagueMmrAdjustmentTests(FollowFixture, TestCase):
    def setUp(self) -> None:
        self.build()
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def adjust(self, *adjustments: int) -> None:
        for adjustment in adjustments:
            LeaguePlayerStats.objects.create(
                user=self.member,
                league_id=next(_steam_league_ids),
                games_played=10,
                mmr_adjustment=adjustment,
            )

    def test_org_change_applies_best_adjustment(self) -> None:
        self.adjust(80, 150)
        set_org_mmr(self.org_user, GameType.DOTA2, 4200, mark_verified=False)
        self.assertEqual(self.league_mmr(self.league_user), 4350)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)
        self.assertEqual(self.league_mmr(self.other_user), 3000)

    def test_bulk_org_change_applies_best_adjustment(self) -> None:
        self.adjust(-40)
        bulk_set_org_mmrs(self.org.pk, GameType.DOTA2, {self.member.pk: 5000})
        self.assertEqual(self.league_mmr(self.league_user), 4960)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)

    def test_adjustment_change_recomputes_every_member_league(self) -> None:
        self.adjust(200)
        with capture_logs() as logs:
            update_user_league_mmr(self.member)
        self.assertEqual(self.league_mmr(self.league_user), 3200)
        self.assertEqual(self.league_mmr(self.other_user), 3200)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)
        events = [e for e in logs if e["event"] == "league_mmr_recomputed"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger"], "adjustment")
        self.assertEqual(
            sorted(events[0]["league_user_ids"]),
            sorted([self.league_user.pk, self.other_user.pk]),
        )

    def test_adjustment_change_without_base_mmr_leaves_league_mmr(self) -> None:
        self.adjust(200)
        OrgUserGameMmr.objects.filter(org_user=self.org_user).delete()
        update_user_league_mmr(self.member)
        self.assertEqual(self.league_mmr(self.league_user), 3000)
        self.assertEqual(self.league_mmr(self.other_user), 3200)

    @override_settings(LEAGUE_MMR_MIN_GAMES=1)
    def test_league_stats_update_applies_adjustment(self) -> None:
        steam_league_id = next(_steam_league_ids)
        match = Match.objects.create(
            match_id=next(_steam_league_ids),
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=steam_league_id,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000101,
            user=self.member,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=3,
            assists=15,
            gold_per_min=550,
            xp_per_min=600,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=0,
        )
        update_all_league_stats_for_league(steam_league_id)
        adjustment = LeaguePlayerStats.objects.get(user=self.member).mmr_adjustment
        self.assertNotEqual(adjustment, 0)
        self.assertEqual(self.league_mmr(self.league_user), 3000 + adjustment)
        self.assertEqual(self.league_mmr(self.other_user), 3000 + adjustment)
        self.assertEqual(self.league_mmr(self.pinned_user), 3300)

    def test_add_league_member_seeds_org_mmr_plus_adjustment(self) -> None:
        self.adjust(120)
        league = self._league("Join League", self.org)
        response = self.client.post(
            f"/api/leagues/{league.pk}/members/",
            {"user_id": self.member.pk},
            format="json",
        )
        self.assertLess(response.status_code, 300, response.content)
        self.assertEqual(
            LeagueUser.objects.nocache().get(user=self.member, league=league).mmr,
            3120,
        )

    def test_tournament_join_seeds_org_mmr_plus_adjustment(self) -> None:
        self.adjust(120)
        league = self._league("Tournament League", self.org)
        tournament = Tournament.objects.create(
            name="Seed Cup", league=league, date_played=timezone.now()
        )
        tournament.users.add(self.member)
        self.assertEqual(
            LeagueUser.objects.nocache().get(user=self.member, league=league).mmr,
            3120,
        )


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
