from typing import Any

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.request import Request
from rest_framework.test import APIClient

from app.models import CustomUser, League
from common.game import GameType
from league.models import LeagueUser
from org.models import Organization
from steam.constants import LEAGUE_ID
from steam.models import LeaguePlayerStats
from steam.tests.league_summary_fixtures import make_player
from steam.views import LeaderboardView
from tests.populate.utils import ensure_org_user

URL = "/api/steam/leaderboard/"


class LeaderboardViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        League.objects.create(name="Leaderboard League", steam_league_id=LEAGUE_ID)
        self._seq = 0

    def _row(self, win_rate: float, games_played: int = 10) -> CustomUser:
        self._seq += 1
        user = make_player(f"lb_user_{self._seq}", 76561198000300000 + self._seq)
        LeaguePlayerStats.objects.create(
            user=user,
            league_id=LEAGUE_ID,
            games_played=games_played,
            win_rate=win_rate,
        )
        return user

    def _results(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        response = self.client.get(URL, params or {})
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def _ordering(self, params: dict[str, str]) -> tuple[str, ...]:
        request = Request(RequestFactory().get(URL, params))
        return tuple(LeaderboardView(request=request).get_queryset().query.order_by)

    def test_default_request_200_sorted_by_win_rate(self) -> None:
        for rate in (0.4, 0.8, 0.6):
            self._row(rate)
        rates = [r["win_rate"] for r in self._results()]
        self.assertEqual(rates, [0.8, 0.6, 0.4])

    def test_league_mmr_sort_key_falls_back_to_win_rate(self) -> None:
        for rate in (0.4, 0.8, 0.6):
            self._row(rate)
        rates = [r["win_rate"] for r in self._results({"sort_by": "league_mmr"})]
        self.assertEqual(rates, [0.8, 0.6, 0.4])

    def test_unknown_sort_key_falls_back(self) -> None:
        for rate in (0.4, 0.8, 0.6):
            self._row(rate)
        rates = [r["win_rate"] for r in self._results({"sort_by": "bogus"})]
        self.assertEqual(rates, [0.8, 0.6, 0.4])

    def _assert_ties_stable(self, order: str) -> None:
        users = [self._row(0.5) for _ in range(3)]
        page1 = self._results({"order": order, "page_size": 2, "page": 1})
        page2 = self._results({"order": order, "page_size": 2, "page": 2})
        ids = [r["user_id"] for r in page1 + page2]
        self.assertEqual(ids, [u.pk for u in users])

    def test_ties_stable_across_pages_desc(self) -> None:
        self._assert_ties_stable("desc")

    def test_ties_stable_across_pages_asc(self) -> None:
        self._assert_ties_stable("asc")

    def test_secondary_sort_by_games(self) -> None:
        few = self._row(0.5, games_played=6)
        many = self._row(0.5, games_played=20)
        for order in ("desc", "asc"):
            with self.subTest(order=order):
                ids = [r["user_id"] for r in self._results({"order": order})]
                self.assertEqual(ids, [many.pk, few.pk])

    def test_games_played_sort_drops_games_tiebreak(self) -> None:
        users = [self._row(rate, games_played=8) for rate in (0.2, 0.9, 0.5)]
        ids = [r["user_id"] for r in self._results({"sort_by": "games_played"})]
        self.assertEqual(ids, [u.pk for u in users])

    def test_ordering_tuple(self) -> None:
        self.assertEqual(self._ordering({}), ("-win_rate", "-games_played", "pk"))
        self.assertEqual(
            self._ordering({"order": "asc"}), ("win_rate", "-games_played", "pk")
        )
        self.assertEqual(
            self._ordering({"sort_by": "games_played"}), ("-games_played", "pk")
        )


class LeaderboardOrgMmrTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.org = Organization.objects.create(name="Leaderboard Org")
        self.league = League.objects.create(
            name="Leaderboard League", steam_league_id=LEAGUE_ID, organization=self.org
        )
        self._seq = 0

    def _row(self) -> CustomUser:
        self._seq += 1
        user = make_player(f"lbo_user_{self._seq}", 76561198000400000 + self._seq)
        org_user = ensure_org_user(
            user,
            self.org,
            mmr=3000 + self._seq,
            game_mmrs={GameType.DEADLOCK: 9000 + self._seq},
        )
        LeagueUser.objects.create(
            user=user, org_user=org_user, league=self.league, mmr=5000 + self._seq
        )
        LeaguePlayerStats.objects.create(
            user=user, league_id=LEAGUE_ID, games_played=10, win_rate=0.5
        )
        return user

    def _get(self) -> tuple[int, list[dict[str, Any]]]:
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries), response.json()["results"]

    def test_leaderboard_reads_dota_org_mmr(self) -> None:
        users = [self._row() for _ in range(2)]
        stranger = make_player("lbo_stranger", 76561198000499999)
        LeaguePlayerStats.objects.create(
            user=stranger, league_id=LEAGUE_ID, games_played=10, win_rate=0.1
        )

        _, results = self._get()

        by_user = {r["user_id"]: r for r in results}
        for i, user in enumerate(users, start=1):
            self.assertEqual(by_user[user.pk]["base_mmr"], 3000 + i)
            self.assertEqual(by_user[user.pk]["league_mmr"], 5000 + i)
        self.assertEqual(by_user[stranger.pk]["base_mmr"], 0)
        self.assertEqual(by_user[stranger.pk]["league_mmr"], 0)

    def test_leaderboard_constant_queries(self) -> None:
        for _ in range(2):
            self._row()
        two, results = self._get()
        self.assertEqual(len(results), 2)
        for _ in range(4):
            self._row()
        six, results = self._get()
        self.assertEqual(len(results), 6)
        self.assertEqual(two, six)

    def test_league_stats_single_reads_dota_org_mmr(self) -> None:
        user = self._row()

        response = self.client.get(f"/api/steam/league-stats/{user.pk}/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["base_mmr"], 3001)
        self.assertEqual(response.json()["league_mmr"], 5001)
