from collections.abc import Callable
from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel
from app.serializers import TournamentSerializer
from app.tests.test_game_org_mmr_drafts import GameOrgMmrFixtures
from common.game import GameType
from events.models import Event, EventState, OrgEventDefaults
from league.models import League, LeagueUser
from league.models_rating import LeagueMatch, LeagueRating
from league.services.match_finalization import LeagueMatchService
from org.features import FeatureKey, set_org_feature
from org.models import Organization, OrgUser, OrgUserGameMmr
from steam.functions.mmr_calculation import update_user_league_mmr
from steam.models import LeaguePlayerStats
from tests.populate.utils import ensure_org_user

RATING_TABLE = '"org_orgusergamemmr"'
_discord_seq = iter(range(880000000000000000, 890000000000000000))


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_seq)),
        positions=PositionsModel.objects.create(),
    )


def _rating_selects(ctx: CaptureQueriesContext) -> int:
    return sum(
        1
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("SELECT") and RATING_TABLE in q["sql"]
    )


def _capture(fn: Callable[[], object]) -> CaptureQueriesContext:
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return ctx


class LeagueFixtures(GameOrgMmrFixtures):
    def member(self, name: str, dota: int, deadlock: int) -> CustomUser:
        user = _make_user(name)
        ensure_org_user(
            user, self.org, mmr=dota, game_mmrs={GameType.DEADLOCK: deadlock}
        )
        return user


class LeagueSnapshotTests(LeagueFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()
        self.players = [
            self.member(f"ls_{i}", 3000 + i * 100, 9000 - i * 100) for i in range(4)
        ]

    def _league_mmrs(self) -> dict[int, int]:
        return dict(
            LeagueUser.objects.filter(league=self.league).values_list("user_id", "mmr")
        )

    def test_signal_snapshots_dota_for_deadlock_tournament(self) -> None:
        ctx = _capture(lambda: self.dl_tournament.users.add(*self.players))

        self.assertEqual(
            self._league_mmrs(),
            {p.pk: 3000 + i * 100 for i, p in enumerate(self.players)},
        )
        self.assertEqual(_rating_selects(ctx), 1)

    def test_signal_creates_org_user_without_rating_row(self) -> None:
        outsider = _make_user("ls_outsider")

        self.dl_tournament.users.add(outsider)

        org_user = OrgUser.objects.get(user=outsider, organization=self.org)
        self.assertFalse(OrgUserGameMmr.objects.filter(org_user=org_user).exists())
        self.assertEqual(self._league_mmrs()[outsider.pk], 0)

    def test_event_defaults_flip_does_not_rekey(self) -> None:
        self.dota_tournament.users.add(self.players[0])
        OrgEventDefaults.objects.update_or_create(
            organization=self.org, defaults={"game_type": GameType.DEADLOCK}
        )

        self.dl_tournament.users.add(self.players[1])
        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())
        LeagueMatchService.finalize(
            match=match,
            winners=[self.players[2]],
            losers=[self.players[3]],
            winning_side="radiant",
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(f"/api/organizations/{self.org.pk}/users/")

        self.assertEqual(self._league_mmrs()[self.players[1].pk], 3100)
        ratings = dict(
            LeagueRating.objects.filter(league=self.league).values_list(
                "player_id", "base_mmr"
            )
        )
        self.assertEqual(ratings, {self.players[2].pk: 3200, self.players[3].pk: 3300})
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["pk"]: row for row in response.json()}
        self.assertEqual(rows[self.players[1].pk]["mmr"], 3100)
        self.assertEqual(rows[self.players[1].pk]["mmr_game_type"], GameType.DOTA2)

    def test_add_league_member_snapshots_mmr(self) -> None:
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": self.players[2].pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._league_mmrs(), {self.players[2].pk: 3200})

    def test_tournament_update_bulk_league_snapshot(self) -> None:
        newcomer = _make_user("ls_newcomer")
        users = [*self.players, newcomer]

        ctx = _capture(
            lambda: TournamentSerializer().update(self.dl_tournament, {"users": users})
        )

        expected = {p.pk: 3000 + i * 100 for i, p in enumerate(self.players)}
        expected[newcomer.pk] = 0
        self.assertEqual(self._league_mmrs(), expected)
        self.assertEqual(_rating_selects(ctx), 1)
        org_user = OrgUser.objects.get(user=newcomer, organization=self.org)
        self.assertFalse(OrgUserGameMmr.objects.filter(org_user=org_user).exists())


class MatchFinalizationGameMmrTests(LeagueFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()
        self.radiant = [self.member(f"mf_r{i}", 2000 + i, 7000 + i) for i in range(5)]
        self.dire = [self.member(f"mf_d{i}", 4000 + i, 1000 + i) for i in range(5)]

    def test_match_finalization_base_mmr_one_map(self) -> None:
        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        ctx = _capture(
            lambda: LeagueMatchService.finalize(
                match=match,
                winners=self.radiant,
                losers=self.dire,
                winning_side="radiant",
            )
        )

        ratings = dict(
            LeagueRating.objects.filter(league=self.league).values_list(
                "player_id", "base_mmr"
            )
        )
        expected = {p.pk: 2000 + i for i, p in enumerate(self.radiant)}
        expected |= {p.pk: 4000 + i for i, p in enumerate(self.dire)}
        self.assertEqual(ratings, expected)
        self.assertEqual(_rating_selects(ctx), 1)

    def test_match_finalization_player_without_org_user(self) -> None:
        stranger = _make_user("mf_stranger")
        match = LeagueMatch.objects.create(league=self.league, played_at=timezone.now())

        LeagueMatchService.finalize(
            match=match,
            winners=[stranger],
            losers=[self.dire[0]],
            winning_side="radiant",
        )

        rating = LeagueRating.objects.get(league=self.league, player=stranger)
        self.assertEqual(rating.base_mmr, 0)


class UpdateUserLeagueMmrTests(LeagueFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()
        self.player = self.member("ul_player", 3500, 8000)
        self.dl_tournament.users.add(self.player)
        self.league.steam_league_id = 4242
        self.league.save(update_fields=["steam_league_id"])
        LeaguePlayerStats.objects.create(
            user=self.player, league_id=4242, games_played=10, mmr_adjustment=120
        )

    def test_update_user_league_mmr_reads_dota(self) -> None:
        update_user_league_mmr(self.player, organization=self.org, league=self.league)

        league_user = LeagueUser.objects.get(user=self.player, league=self.league)
        self.assertEqual(league_user.mmr, 3620)

    def test_update_user_league_mmr_deadlock_only_member_gets_zero(self) -> None:
        ensure_org_user(self.player, self.org, mmr=0)

        update_user_league_mmr(self.player, organization=self.org, league=self.league)

        league_user = LeagueUser.objects.get(user=self.player, league=self.league)
        self.assertEqual(league_user.mmr, 0)


class OrgUserCreationSitesTests(TestCase):
    def setUp(self) -> None:
        self.site_admin = CustomUser.objects.create_user(
            username="cs_site_admin", password="x", is_staff=True, is_superuser=True
        )
        self.org = Organization.objects.create(name="Creation Org")
        self.client = APIClient()
        self.client.force_authenticate(self.site_admin)

    def _assert_created_without_rows(
        self, user: CustomUser, org: Organization, response: object
    ) -> None:
        self.assertLess(response.status_code, 300, response.content)
        org_user = OrgUser.objects.get(user=user, organization=org)
        self.assertFalse(OrgUserGameMmr.objects.filter(org_user=org_user).exists())

    def test_org_user_creation_sites_write_no_rows(self) -> None:
        league = League.objects.create(name="Creation League", organization=self.org)
        set_org_feature(
            self.org, FeatureKey.PROMOTION, enabled=True, actor=self.site_admin
        )
        event = Event.objects.create(
            name="Creation Event",
            organization=self.org,
            game_type=GameType.DEADLOCK,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            min_players=2,
            max_players=10,
        )
        posts: list[tuple[str, str, dict[str, object]]] = [
            ("add_org_admin", f"/api/organizations/{self.org.pk}/admins/", {}),
            ("add_org_staff", f"/api/organizations/{self.org.pk}/staff/", {}),
            ("add_org_member", f"/api/organizations/{self.org.pk}/members/", {}),
            ("add_league_member", f"/api/leagues/{league.pk}/members/", {}),
            ("org_promoters", f"/api/organizations/{self.org.pk}/promoters/", {}),
        ]
        for name, url, extra in posts:
            with self.subTest(site=name):
                user = _make_user(f"cs_{name}")
                response = self.client.post(
                    url, {"user_id": user.pk, **extra}, format="json"
                )
                self._assert_created_without_rows(user, self.org, response)

        with self.subTest(site="organization_create"):
            creator = _make_user("cs_creator")
            client = APIClient()
            client.force_authenticate(creator)
            response = client.post(
                "/api/organizations/", {"name": "Created Org"}, format="json"
            )
            created = Organization.objects.get(name="Created Org")
            self._assert_created_without_rows(creator, created, response)

        with self.subTest(site="event_signup"):
            signer = _make_user("cs_signer")
            client = APIClient()
            client.force_authenticate(signer)
            response = client.post(
                f"/api/events/{event.pk}/signup/",
                {"intent": "rsvp", "profile": {}},
                format="json",
            )
            self._assert_created_without_rows(signer, self.org, response)
